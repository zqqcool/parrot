# OpenAI-compatible 模型接入与能力协商契约

> 状态：研究记录，非实施依据
> 适用线协议：`POST /chat/completions` 与 SSE `data:` 流
> 日期：2026-07-19

> Provider 适配以 [Agent Runtime 可落地实施方案](agent-runtime-implementation-plan.md) 为基线；多能力控制流以
> [Skill、MCP 与 Subagent 最终编排方案](multi-capability-orchestration-design.md) 为准。首期只增加 `finish_reason`
> 和必要的私有 Provider 状态，不建设动态 Capability Profile、启动探测或按模型名称适配。本文件保留兼容性风险和
> 长期合同研究。

> 2026-07-21 原则修订：下文 Requirement/Observation/Completion Gate 与 `tool_choice=required` 降级方案不直接作为通用
> Provider 合同；完成证据、等待态和必做业务流程由 Parrot Runtime/应用服务拥有，Tool 调用安全
> 由 allowlist、Schema、tenant/binding、Policy、审批和回执保证。

## 1. 决策

Parrot 不针对某个模型或厂商设计业务 Runtime，只支持一条 OpenAI-compatible Chat Completions 线协议。但
“请求长得像 OpenAI”不代表端点行为完全一致，因此需要把差异收敛到版本化 Capability Profile 与 Provider
Adapter，而不是在 Planner、Tool Loop、Memory 或知识逻辑中判断模型名称。

核心规则：

1. 业务模块只依赖 Provider 无关的 `ModelTurn`、`ModelStreamEvent` 和 `ModelCapabilityProfile`。
2. 默认使用最小兼容基线：`system/user/assistant/tool`、字符串 content、function tools、assistant
   `tool_calls`、`tool_call_id` 和 SSE deltas。
3. `developer`、message `name`、strict schema、parallel tool calls、forced tool choice、stream usage、Reasoning
   字段和特殊 thinking 参数均为可选能力。
4. 不按 model 字符串猜能力。每个租户 LLM Config 保存服务端确认的 Capability Profile、探测版本与时间。
5. Tool 确定性由 `Requirement/Observation/Completion Gate` 保证；Provider 的 `tool_choice` 和 strict schema
   只是增强，不能作为唯一正确性边界。
6. Reasoning 永不公开；如果端点要求在 Tool Loop 回传特殊状态，Adapter 必须无损保存和重放。
7. 无工具 finalizing 是统一公开边界。模型在执行阶段输出的 narration 不直接发给用户。

## 2. 当前实现的事实与风险

当前 `OpenAiCompatibleModelClient` 已具备：

- `/chat/completions` HTTP 请求；
- `system/user/assistant/tool` messages；
- function tool definitions；
- 非流式和 SSE 流式 content/tool call delta；
- 归一化 `finish_reason`；
- 可选 `reasoning_content`/reasoning delta 的私有解析，以及 Tool continuation 回传；
- Planner/Intent 的普通 JSON 对象及单层严格 `json` Markdown fence 兼容；
- URL、HTTPS、Host allowlist 和凭据解密；
- retryable Provider error 分类。

当前首期内部合同表达：

```python
ChatCompletion(
    content,
    tool_calls,
    content_deltas,
    finish_reason,
    reasoning_content,
    reasoning_deltas,
)
ChatCompletionDelta(
    content_delta,
    tool_call_deltas,
    finish_reason,
    reasoning_content_delta,
)
```

仍未进入首期合同的能力包括：

- Provider message/response id；
- refusal/error event；
- `reasoning_content` 之外、Tool Loop 可能必须重放的 opaque provider state；
- JSON Schema/strict/tool choice/parallel 能力；
- content phase 或“现在是否是 final”的增强信号。

当前基线已移除按 `provider` 名称执行的请求分支。`provider` 只保存供应商显示标识，所有端点统一接收
OpenAI-compatible Chat Completions 基线请求。管理接口显式暴露 `thinking_enabled` 与
`prompt_cache_enabled`，默认关闭，由管理员按端点的实际模式确认；这两个字段表达 Runtime 兼容意图，
不得用模型名称猜测。`thinking_enabled` 不翻译成厂商私有请求字段；`prompt_cache_enabled=true` 时
Adapter 才可发送稳定的 `prompt_cache_key`，并在流式请求附带 `stream_options.include_usage`。响应中若出现
`usage` / `prompt_tokens_details.cached_tokens`，则解析进 `ChatCompletion.usage`，写入 management-only
`model.response` 诊断；端点不返回 usage 时行为与关闭时相同，不得失败。

响应解析仍以 Provider 无关方式兼容可选 `reasoning_content`，并在 Tool continuation 时私有回传；该内容不会进入
公开事件。这不能推导所有 OpenAI-compatible 端点都使用相同字段。后续若确有端点需要 opaque provider state，
应继续收敛在 Adapter 内，而不是把 provider `if` 散落到 Planner、Tool Loop 或知识逻辑中。

本地真实端点还验证了一个与模型名称无关的输出差异：即使明确要求“仅返回 JSON”，端点仍可能偶发包裹一层
Markdown `json` fence。Runtime 只兼容完整响应恰好为一个 JSON 对象或一个严格单 fence 的情况；不得从前后解释
文字、多个 fence 或任意自然语言中扫描 JSON，否则控制面会重新引入歧义和 Prompt Injection 风险。

## 3. OpenAI-compatible 的项目定义

Parrot 声明支持的是：

```text
protocol_family = openai_chat_completions
protocol_version = parrot-v1
```

### 3.1 必需基线

端点必须支持：

- `POST {base_url}/chat/completions`；
- Bearer credential；
- `model`、`messages`；
- `system/user/assistant` 文本消息；
- `stream=false` 普通响应；
- `stream=true` 且以 `data:` JSON 与 `[DONE]` 结束；
- 正常错误使用 HTTP 非 2xx；
- 至少一个可工作的 `max_tokens` 或经配置映射后的输出限制字段。

### 3.2 Agent 必需扩展

要绑定功能型或需要 Tool 的知识型 Agent，还必须支持：

- `tools=[{type:function,...}]`；
- assistant `tool_calls`；
- tool message `tool_call_id`；
- 工具结果回传后继续生成；
- 流式 Tool Call argument 聚合，或明确只允许非流式 Tool 回合。

不满足 Agent 扩展的端点只能用于 `tools=()` 的纯文本场景，管理端必须明确显示，不能运行时静默尝试。

## 4. `ModelCapabilityProfile`

```python
@dataclass(frozen=True)
class ModelCapabilityProfile:
    version: Literal["v1"]
    protocol_family: Literal["openai_chat_completions"]
    endpoint_mode: Literal["chat_completions"]

    supports_streaming: bool
    supports_tools: bool
    supports_streaming_tool_calls: bool
    supports_parallel_tool_calls: bool

    tool_choice_auto: bool
    tool_choice_none: bool
    tool_choice_required: bool
    tool_choice_named: bool
    supports_allowed_tools: bool

    supports_strict_tool_schema: bool
    supports_json_object: bool
    supports_json_schema: bool

    supports_developer_role: bool
    supports_message_name: bool
    supports_stream_usage: bool

    reasoning_transport: Literal[
        "none",
        "reasoning_content",
        "content_blocks",
        "opaque",
    ]
    reasoning_replay: Literal["none", "required_on_tool_continuation"]
    thinking_request_strategy: str | None

    max_tools_per_request: int | None
    max_parallel_calls_per_turn: int | None
    verified_at: datetime
    probe_version: str
    status: Literal["verified", "partially_verified", "failed", "stale"]
```

Profile 是服务端拥有的事实，不能由前端随请求传入，也不能由模型自行声明。

### 4.1 配置来源

优先级：

```text
项目内置 conservative baseline
< 管理员显式配置
< conformance probe 已验证结果
```

显式配置可以关闭能力；开启高风险能力必须有 probe 或受支持端点的受控 preset。不要让“管理员勾选支持 strict”
替代实际验证。

## 5. 为什么不能只看 Provider/Model 名称

同名模型可能被部署在：

- 官方 API；
- vLLM；
- 云厂商网关；
- 自建代理或协议转换层；
- 不同 chat template/tool parser 配置。

vLLM 官方文档要求为不同模型选择匹配的 tool-call parser 和 chat template；在 auto 模式且没有 strict 约束时，
它可能从原始文本解析 Tool Call，参数偶尔会不符合 Schema。不同版本对 `required`、named、并行和 strict 的支持
也不同。因此 `model="..."` 不能证明端点能力。

## 6. Conformance Probe

LLM Config 创建或管理员主动验证时，运行低风险探测：

1. **Plain**：固定短文本，验证基本响应和 finish reason；
2. **Streaming**：验证 SSE、delta 顺序、`[DONE]` 和空 delta；
3. **Single tool**：`auto` 下触发一个固定纯函数 Tool；
4. **Tool continuation**：回传 Tool Result，验证能正常 final；
5. **Required/named/none**：分别验证支持或明确失败；
6. **Parallel**：请求两个独立纯函数，验证一个 turn 是否返回多个 call；
7. **Strict tool schema**：使用 `additionalProperties=false`、全部字段 required 的 Schema；
8. **Structured output**：分别验证 json object/schema；
9. **Thinking**：启用配置后触发 Tool Loop，验证 Reasoning 字段、回传要求和公开 content；
10. **Streaming interruption**：验证中断错误是否可识别，不能把半截 Tool JSON 当文本。

探测要求：

- 使用专用无副作用 Tool；
- 不发送租户业务数据；
- 限制 Token、请求数和超时；
- 保存摘要、响应 shape fingerprint 和错误码，不默认保存 raw Reasoning；
- `verified_at` 过期、端点/model/template 变化后标记 stale；
- 探测失败不能影响既有运行，先回退 conservative profile。

## 7. Provider 无关的 Model Turn

```python
@dataclass(frozen=True)
class ModelTurn:
    message_id: str | None
    content: str | None
    reasoning: str | None
    tool_calls: tuple[ToolCall, ...]
    finish_reason: Literal[
        "stop",
        "tool_calls",
        "length",
        "content_filter",
        "cancelled",
        "error",
        "unknown",
    ]
    provider_state: ProviderTurnState | None
    usage: ModelUsage | None

@dataclass(frozen=True)
class ModelStreamEvent:
    type: Literal[
        "content_delta",
        "reasoning_delta",
        "tool_call_delta",
        "usage",
        "finish",
        "provider_state",
        "error",
    ]
    sequence: int
    payload: object
```

`ProviderTurnState` 是 Adapter 私有、可安全持久化的结构，只供同一 Tool Loop 恢复。Runtime 不解析其中 Reasoning
语义，Channel 也不能读取。

## 8. Tool Call 确定性

### 8.1 Provider 能保证什么

在支持的端点上：

- `tool_choice=required` 可以要求至少一个 Tool；
- named choice 可以要求某个 Tool；
- `strict=true` 可以提高参数符合 Schema 的确定性；
- `parallel_tool_calls` 可以允许一个 turn 多个 Tool Call。

OpenAI 官方仍将 `auto` 定义为可调用 0、1 或多个函数。并行也只是“模型可以返回多个”，不是 Runtime 必须并行
执行。Chat Completions 的 Tool strict 默认并不会自动开启。

当前已实施的最小合同不按 provider/model 名称分支：普通 Agent Loop 在提供工具时显式发送 `auto`；知识型
instruction-only Skill 成功激活后发送 `required`；若需要纠正违规普通文本，则只发送 `ask_user` 和
`final_response` 两个终止工具。未提供工具的 Planner/Final Renderer 不发送 `tool_choice`。配置的端点若不支持
OpenAI-compatible `required`，请求应失败闭合并由运营诊断暴露，不能静默回退到 `auto`，否则会重新引入提前结束。

### 8.2 Runtime 必须保证什么

```python
if turn.tool_calls:
    validated = validate_authorize_and_schedule(turn.tool_calls)
    observations = execute(validated)
    ledger.record(observations)
    continue_loop()

elif completion_gate.can_finalize(requirements, observations, turn):
    enter_finalizing()

elif correction_budget.remaining:
    retry_with_bounded_correction()

else:
    partial_failed_or_waiting_user()
```

因此：

```text
没有 Tool Call != 任务完成
模型说“成功” != 外部动作成功
Tool 返回错误 != Requirement 已满足
```

功能型 Planner、知识型 Interpreter、TaskBoard 和服务端规则负责创建 `Requirement`；只有授权并成功的
`Observation` 能满足它。

### 8.3 当 forced tool 不可用

- 不发送端点不支持的 `required/named`；
- Runtime 保留 Requirement，拒绝 early final；
- 有界纠正一次；
- 如果参数已经由受限计划确定且 Tool Policy 允许，Runtime 可以直接执行只读 Tool；
- 写/外部副作用仍必须走正常审批和幂等合同；
- 不能完成时返回 partial/failed/waiting_user，不伪造结果。

这使 Thinking 与 Tool Choice 的 Provider 限制不会中断整个业务 Loop。

## 9. Structured Output

Planner、KnowledgeTurnInterpreter、DelegationPlan 和 Result Schema 使用同一策略：

```text
supports_json_schema
→ native JSON Schema

else supports_json_object
→ JSON object + application schema validation

else
→ plain content + strict JSON parser + application schema validation
```

任何路径都必须做应用层 Schema 校验。非法输出最多进行一次受限修复；修复提示只包含验证错误和原始有限输出，
不能无限递归或直接降级成 `direct_answer`。

Tool Schema 的 strict 版本应满足 OpenAI 约束：每个 object `additionalProperties=false`，properties 全部列入
required，可选值使用 nullable union。端点不支持时保留同一应用 Schema，只关闭线协议 strict。

## 10. 并行 Tool Call

需要区分：

```text
Provider capability:
  一个模型 turn 能否输出多个 tool_calls

Runtime policy:
  哪些调用可以同时执行、每个域允许多少并发
```

即使 `supports_parallel_tool_calls=true`，Runtime 仍按以下条件分批：

- 只读/幂等与副作用；
- shared resource/connection/domain；
- Tool 间依赖；
- 审批状态；
- Tenant/Provider 限流；
- 结果顺序和失败隔离。

端点不支持 parallel tool calls 时，知识库/MCP 的确定性 Evidence fan-out 和持久化 Subagent fan-out仍可由 Runtime
并行执行；不能把所有并行能力绑在模型是否一次返回多个 call 上。

## 11. Thinking / Reasoning

### 11.1 通用原则

- `thinking_enabled` 是 Runtime 意图，不等于固定请求字段；
- 默认值为 `false`，只能由有模型配置管理权限的管理员显式开启，并随 Runtime profile snapshot 持久化；
- 管理员必须让该声明与上游端点的真实模式一致，Runtime 不根据 provider/model 名称猜测；
- Reasoning delta/content 始终进入内部 Trace/opaque state，不进入公开 Output；
- 未知字段默认忽略展示但保留兼容性诊断，不能当普通 content；
- Tool Loop 需要回传的状态必须与对应 assistant tool call 一起持久化；
- 一个运行中不能无依据切换会破坏 continuation 的 thinking mode。

### 11.2 Tool Choice 兼容策略

当前 Runtime 使用三层、与模型名称无关的保护：

```text
thinking_enabled=true
  -> 本次 Run 始终使用 tool_choice=auto

thinking_enabled=false，但响应出现 reasoning_content
  -> 后续 turn 禁止 required，改用 auto

端点以 400/422 明确拒绝 tool_choice=required
  -> 同一 turn 立即以 auto 重试，并在本次 Run 后续保持 auto
```

活动 Skill 的结构化终止仍由完成门保证：普通文本不会因为降级为 `auto` 就直接公开，而会进入一次只暴露
`ask_user` 与 `final_response` 的纠正轮。字段拒绝必须记录 `tool_choice_fallback` 诊断；其他 400/422 仍按正常
Provider 错误失败闭合。这样兼顾支持强制 Tool Choice 的普通端点与不支持它的思考端点。

未验证端点不发送未知的 thinking/reasoning 开关。若未来需要厂商扩展，只能在显式 Adapter capability 中实现，
不得通过 provider/model 名称分支散落到 Agent Loop。

### 11.3 Prompt Cache

- `prompt_cache_enabled` 是管理员声明的端点能力，默认 `false`，随 Runtime profile snapshot 持久化；
- 开启后 Adapter 发送 `prompt_cache_key=parrot:llm:{llm_id}`；流式请求可附带 `stream_options.include_usage`；
- 响应 `usage` / `cached_tokens` 仅进入 management-only `model.response`；端点不返回时不得失败；
- 不得按 provider/model 名称自动开启。

### 11.3 最终输出

执行阶段出现 content + tool_calls 时，content 视为 internal narration。取证/动作完成后显式进入：

```text
FINALIZING
tools=()
```

只有该调用的 content delta 通过 durable-live Publisher。Root WebSocket 在 `thinking_enabled` 时可公开
`ai.thinking.*`；否则 Reasoning 不展示。最终 `finish_reason=stop`、无 Tool Call 且 Completion Gate 满足后完成
Interaction。

## 12. Prompt/Role 兼容

基线只依赖：

```text
system
user
assistant
tool
```

Adapter 规则：

- `developer_role=false`：Agent Profile 合并到单一 system prefix；
- `message_name=false`：删除 name，边界保留在结构化内容中；
- Tool Call/Result 必须保持 ID 和顺序；
- 不支持多 system 的端点永远只收到一个 system；
- 不支持复杂 content blocks 时只发文本或工具字段；
- Context 内部信任与类型不依赖 wire role/name。

## 13. 错误与降级

| 错误 | Runtime 行为 |
| --- | --- |
| 400 unknown field | 标记 capability mismatch；当前请求按保守策略最多重试一次 |
| 400 missing reasoning replay | Adapter contract failure；禁止丢状态重试，记录并安全失败 |
| malformed tool JSON | 不执行；Schema failure，受限修复/失败 |
| tool name 不存在 | 不执行；把可公开安全错误返回 Loop 或失败 |
| finish=length 且有半截 Tool | 不执行；增加 Budget 或失败，不能解析猜测 |
| 408/429/5xx | 在总 Budget 内指数退避；遵守 Retry-After |
| stream 中断 | final 输出按 durable reset/recovery；Tool 不重复执行 |
| content_filter/refusal | 不作为正常 final；转换为稳定失败/安全答复 |
| capability stale | 回退 baseline 并调度后台 re-probe |

重试必须区分“模型生成重试”和“外部 Tool 重试”。已成功的副作用 Tool 不能因为 Provider final 失败而重跑。

## 14. 数据模型与管理端

`llm_configs` 建议新增版本化能力字段，使用新 Migration：

```text
capability_profile JSONB NOT NULL
capability_status VARCHAR
capability_verified_at TIMESTAMP
capability_probe_version VARCHAR
endpoint_fingerprint VARCHAR
```

管理端显示业务语言：

- 文本生成：可用/不可用；
- 流式输出：已验证/未验证；
- 工具调用：已验证/仅单工具/不可用；
- 并行工具：已验证/未验证；
- 结构化输出：严格/应用校验/不可用；
- 思考模式：可用但内部/不可用/需要重新验证。

不要让用户维护 tool parser、reasoning field 或内部 capability key。高级诊断可以只读显示 probe 结果。

## 15. 模块边界

```text
backend/app/modules/agent_runtime/provider/
  contracts.py          # ModelTurn/ModelStreamEvent/CapabilityProfile
  openai_chat.py        # baseline request/response transport
  capabilities.py       # feature strategy selection
  reasoning.py          # opaque reasoning request/replay strategy
  structured_output.py  # schema strategy
  conformance.py        # safe admin probe
  errors.py             # normalized error taxonomy
```

现有 `openai_compatible.py` 应拆分，但 HTTP Host allowlist、HTTPS、凭据解密和 retryable error 继续保留。业务模块不得
import 某厂商 strategy。

## 16. 可观测性

每次模型调用记录：

- llm config id、model、endpoint fingerprint，不记录 credential；
- capability profile version/status；
- stage：planner/interpreter/execution/finalizing/subagent；
- stream、tool choice、strict、parallel、thinking strategy；
- request/response/finish time；
- first reasoning/content/tool delta time；
- finish reason、Tool count、schema validation；
- usage/cached/reasoning tokens（可用时）；
- retry、capability mismatch 和降级原因。

Raw Prompt 与原始模型响应只允许显式本地诊断；生产诊断仅保存角色、工具名、`tool_choice`、内容长度、
`finish_reason` 等元数据。任何环境都不保存 Reasoning；生产日志禁止输出完整 Prompt、模型正文、Memory、
Tool Result 和凭据。

## 17. 测试

### 17.1 Baseline Contract

- plain/stream/content/tool call/tool result continuation；
- SSE 注释、空行、空 delta、`[DONE]`；
- finish reason 和 usage；
- 多 Tool delta 按 index 聚合；
- malformed JSON、未知 role/field、HTTP 错误。

### 17.2 Capability Matrix

构造 Fake Provider：

- baseline only；
- tools but no parallel；
- no required/named；
- strict supported/unsupported；
- developer/name supported/unsupported；
- reasoning_content replay required；
- stream tool calls unsupported；
- capability changed after verification。

### 17.3 Determinism

- required observation 未满足时 text stop 不结束；
- named/required 不支持时有界修复；
- strict 失败不执行 Tool；
- Tool 成功/失败分别更新 Observation；
- write success 来源于真实 Tool receipt；
- Provider final 重试不重放 Tool。

### 17.4 Thinking

- Reasoning 不进入公开事件；
- Tool continuation 完整回传 Provider State；
- 缺失 replay state 安全失败；
- content + tool_calls 的 pre-tool narration 不公开；
- finalizing tools=() 实时输出 content。

### 17.5 Cross-provider

相同 Provider-neutral fixtures 在至少三类端点跑合同测试：

```text
reference OpenAI-compatible endpoint
vLLM endpoint with configured parser/template
another vendor-compatible endpoint
```

测试的是已声明能力，不以厂商名称写预期。CI 可使用 Fake Provider 覆盖全部分支，真实端点作为受控集成测试。

## 18. 实施顺序

### Phase A：标准事件

- 扩展 Completion/Delta：finish reason、reasoning、usage、provider state；
- 保持现有请求字段和公开行为；
- 添加 Fake Provider contract tests。

### Phase B：Capability Profile

- 新 Migration 与 Runtime Catalog；
- conservative baseline；
- 管理端 safe probe；
- 移除业务层 provider/model 判断。

### Phase C：Structured/Tool Strategy

- Planner、Interpreter、DelegationPlan 接入 schema strategy；
- Tool choice/strict/parallel 由 capability 驱动；
- Completion Gate 覆盖 unsupported forced-tool 场景。

### Phase D：Reasoning State

- 实现 opaque state 保存/回传；
- 修复 DeepSeek-compatible Tool Loop；
- 扩展其他端点时只增加 Adapter Strategy 和 contract fixture。

### Phase E：清理

- 将 `provider` 字段收敛为协议/显示标签，不再作为业务 feature switch；
- 删除直接 `if provider == ...`；
- 记录支持矩阵与 re-probe 运维手册。

## 19. 明确不采用

### 19.1 “都叫 OpenAI-compatible，所以行为相同”

不采用。Tool Parser、Chat Template、strict、Reasoning 和 continuation 均可能不同。

### 19.2 按模型名称维护 if/else

不采用。同名模型在不同部署上的行为可不同，升级后也会漂移。

### 19.3 为每个厂商建立一套 Agent Loop

不采用。差异只属于 Adapter Strategy，Planner/TaskBoard/Completion Gate/Publisher 必须统一。

### 19.4 Thinking 时关闭 Tool 或强制所有模型 final_response

不采用。Thinking 与 Tool 可以共存，但 forced choice/replay 约束不同；Runtime Completion Gate 才是统一保证。

### 19.5 把 Raw Reasoning 发给用户或存公开消息

不采用。Reasoning 属于非公开 Provider State/Trace，最终答案单独生成和公开。

## 20. 参考

- [OpenAI Function calling](https://developers.openai.com/api/docs/guides/function-calling)：`tool_choice`、并行
  Tool Call 与 strict schema 的官方语义；Parrot 只采纳 Chat Completions 可表达的部分。
- [OpenAI Structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs)：原生 JSON Schema
  能力与应用层验证的参考。
- [OpenAI Prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching)：稳定前缀和动态后缀的
  性能原则。
- [vLLM Tool Calling](https://docs.vllm.ai/en/stable/features/tool_calling/)：OpenAI-compatible 服务仍依赖模型
  对应 Tool Parser、Chat Template 和版本能力。
- [DeepSeek Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode)：Thinking + Tool Call 时的
  `reasoning_content` continuation 要求。

## 21. 验收标准

1. Runtime 不因模型/厂商名称分叉业务流程；
2. 每个 LLM Config 有已验证或保守的 Capability Profile；
3. Provider 不支持的 feature 不会被盲目发送；
4. Planner/Interpreter/Tool 参数始终经过应用 Schema 校验；
5. Tool 选择错误不会让未完成任务提前成功；
6. Thinking Tool Loop 所需状态可无损恢复且不会公开；
7. Provider Tool 并行与 Runtime 执行并发是两个可独立控制的层；
8. 同一内部 Context/Task/Completion 合同可在不同 OpenAI-compatible 端点运行；
9. 端点升级或能力漂移可被探测、回退和观测。
