# Backend Harness Standard

## 目录标准

推荐后端按 route、application service、runtime port 分层：

```text
app/
  api/routes/im_websocket.py
  modules/im/
    service.py
    entry_service.py
  modules/interactions/
    schemas.py
    service.py
    runtime.py
```

## 统一请求模型

所有入口必须转换为统一请求：

```pseudo
type HarnessRequest:
    request_id: string
    actor_id: string
    entry_type: "websocket"
    input_type: "text"
    input: HarnessInput
    context_refs: list<ContextRef>
    options: HarnessOptions
    idempotency_key: string
```

```pseudo
type HarnessInput:
    text: string optional
    file_refs: list<string>
    metadata: map<string, any>
```

## Adapter 接口标准

```pseudo
interface EntryAdapter:
    function validate(rawRequest): void
    function toHarnessRequest(rawRequest, requestContext): HarnessRequest
```

语音 adapter 当前未启用。未来启用时必须保持独立入口状态和 adapter，并转换到同一
`HarnessRequest`，不得修改文本入口的 API 或运行时状态机。

WebSocket adapter：

```pseudo
class WebsocketAdapter implements EntryAdapter:
    function validate(raw):
        requireNotBlank(raw.text)
        requireLength(raw.text, min = 1, max = MAX_INPUT_CHARS)

    function toHarnessRequest(raw, ctx):
        return HarnessRequest(
            request_id = ctx.request_id,
            actor_id = ctx.actor_id,
            entry_type = "websocket",
            input_type = "text",
            input = HarnessInput(
                text = normalizeWhitespace(raw.text),
                file_refs = raw.file_refs,
                metadata = { "source": "websocket", "channel_id": ctx.channel_id }
            ),
            context_refs = raw.context_refs,
            options = raw.options,
            idempotency_key = ctx.idempotency_key
        )
```

## Harness 编排标准

```pseudo
class AiHarness:
    function run(request):
        validateHarnessRequest(request)

        return idempotency.runOnce(request.idempotency_key, () => {
            policyDecision = policy.evaluate(request)
            if policyDecision.denied:
                throw HarnessError("AI_POLICY_DENIED")

            context = contextBuilder.build(
                actor_id = request.actor_id,
                input = request.input,
                refs = request.context_refs
            )

            executionPlan = modelPlanner.plan(
                input = request.input,
                context = context,
                options = request.options
            )

            stream = modelExecutor.stream(executionPlan)
            return outputStreamer.forward(stream, {
                request_id = request.request_id,
                entry_type = request.entry_type
            })
        })
```

## Agent 配置与发布门禁

智能体必须先以草稿创建，再绑定至少一个启用的 LLM、指定唯一默认 LLM，最后发布。
绑定的 Skill 必须处于已发布状态。LLM、Skill 的状态验证由各自模块通过 typed port 提供，
`agents` 模块不得直接读取其私有表。

```pseudo
function ensurePublishable(tenantId, agentId):
    llmBindings = agentBindings.getLlmBindings(tenantId, agentId)
    require(llmBindings.defaultId exists, "AGENT_LLM_REQUIRED")
    llmCatalog.validateActive(tenantId, llmBindings.ids)

    skillIds = agentBindings.getSkillBindings(tenantId, agentId)
    skillCatalog.validatePublished(tenantId, skillIds)
```

发布和下线要求 `agents.publish`，配置绑定要求 `agents.manage`。所有写入必须追加审计记录。

## Runtime 执行边界

## LLM 配置与密钥边界

LLM 配置是当前租户的 Parrot 持久化对象，不依赖 DataCenter 或任何外部凭据服务。创建配置时
一并提交 API Key，服务端使用独立部署主密钥执行 AES-256-GCM 加密后落库；查询接口只返回
`credential_configured`，不返回明文或密文。编辑时未提交 API Key 表示保留原密文。

部署主密钥由 `security.credential_encryption_key` 提供，只能位于仓库外 secrets 文件或经批准的
KMS 中，不能与数据库备份放在同一安全域。运行时只在供应商调用前于进程内解密，明文不得进入
审计日志、事件、浏览器响应或工具 observation。

`temperature` 和 `max_tokens` 是每个 LLM 配置的运行参数。运行时将 `max_tokens` 额外限制为
全局 `ai.agent_max_output_tokens` 的安全上限。`provider` 只是供应商显示标识，不参与 Runtime
分支；所有配置统一使用 OpenAI-compatible Chat Completions 基线。当前实现不发送任何供应商私有
thinking 请求字段，未经能力协商验证的扩展参数不得进入请求。

Parrot 只通过进程内 `RuntimePort` 调度自己的 Agent runtime。该 port 只接受并快照
interaction；独立 runtime worker 通过 PostgreSQL 租约执行 Agent loop。不存在远程 Skyler
适配器，也不得由 router 或 interaction service 直接导入 Skyler 模块。

```pseudo
interaction = persistAcceptedInteraction(request)
commit(interaction)

runtimeResult = runtime.prepare(
    principal = trustedPrincipal,
    request = RuntimeRequest(interaction_id, runtime_agent_id, input),
)

persist(interaction.runtime_execution_id = runtimeResult.execution_id)
commit(interaction)
runtime.dispatch(request)

taskiq.runtime.execute(tenantId, interactionId):
    require durable input and profile snapshot
    acquire execution lease
    execute agent loop
    persist terminal event before notification
```

要求：

- Runtime 事件先持久化再进入 WebSocket；公开客户端只消费允许列表中的 `ai.output.*` 事件，其他
  `ai.*` 事件保留给受权管理面或内部流程。事件过滤仍必须推进 replay sequence。
- TaskIQ runtime task 只处理消息指定的 tenant/interation；它对 `accepted`/`running` interaction
  获取 PostgreSQL 租约。执行过程中必须
  周期性续租，所有 worker 事件必须携带领取者 fencing owner，终态事件和显式释放必须只影响
  同一 owner；不得依赖 Web 进程内存中的后台 task 作为恢复机制。
- 已提交且可立即执行的 interaction 直接投递 TaskIQ worker；scheduler 只处理业务指定时刻和
  有界延迟重试。投递前必须提交 runtime execution metadata，避免 worker 领取后被 Web 请求中的
  旧状态覆盖。
- interaction、TaskBoard、会话消息、记忆索引和 schedule execution 均是 Parrot 持久化对象；
  恢复只使用这些对象，不读取任何外部 runtime 状态。
- Root Interaction 的会话账本使用单调 `sequence` 保存首条用户输入、每次 waiting 问题、每次 steer 补充和最终回答；
  同一 Interaction 不得再以 role 唯一键压缩为一条 user 和一条 assistant。
- Runtime 错误映射为稳定错误码，不得返回堆栈、内部地址或凭证。

## 进程内 Agent Runtime

Parrot 运行时使用 Agent profile resolver：它只会解析当前
tenant 内、且已绑定到当前 Agent 的启用 LLM、已发布 Skill 和 MCP。客户端和 Skill 包都不能指定
或覆盖模型、租户、能力范围。所有第三方 Skill/MCP 都是租户私有资源，必须由管理员显式绑定；
未绑定的资源不得被发现或执行。

功能型 Agent 的执行步骤为：Planner 选择直接回答、进入 Agent Loop、能力检索或子任务编排。Planner
不直接澄清；只有 Root WebSocket Agent Loop 可用 `ask_user` 以 `waiting_user_input` 结束当前模型回合。
interaction 仍可恢复：同一所有者的 `steer` 必须原子地
写入控制事件、清除上一轮 waiting lease、重新置为可领取状态，并在事务提交后直接投递 TaskIQ；worker
随后使用原始请求、最近澄清问题和新补充内容重新规划。运行中的普通 `steer` 只进入控制事件流，不重复
投递任务；
子任务计划必须先通过精确 source span、依赖、
预算和深度校验，之后由 runtime 自动分派。Agent loop 只暴露当前计划允许的工具，未暴露的模型
调用一律拒绝。内建 `memory`、`todo`、`time` 和 `math` 始终受运行时输入边界约束；`script`
默认关闭，只有 `[runtime.script].enabled = true` 且 Skill sandbox 可用时才暴露。
Skill 必须经过 `find_and_load`（或等价的 `find` → `load`）再 `capability_execute`；可执行 ZIP Skill 和可选 script 均必须在
生产环境的 Bubblewrap sandbox 中运行。`local`/测试配置可以显式启用受控本地子进程来联调，但不得复用为
生产配置；MCP 仅通过配置的 HTTP/SSE/stdio transport、主机 allowlist 与数据库加密凭据执行。
模型只接收经长度、层级、列表数量限制且已脱敏的工具 observation；完整相同或达到相似度阈值的
`capability_execute` 会被拒绝并要求综合已有结果。无副作用内置查询、知识检索，以及管理员显式标记
`parallel_safe=true` 且仍通过实时 Schema/Policy 校验的自动只读 MCP 可在同一轮中受限并行；其他工具形成串行屏障。

MCP 自动执行权限来自管理员持久化的逐 Tool Policy，而不是远端 `readOnlyHint`。Policy 必须保存 Tool 名、说明、
JSON Schema、服务端计算的 canonical schema hash、`effect=read|side_effect` 和
`approval=automatic|required`，以及缺省为 false 的 `parallel_safe`。只有 `read + automatic` 可自动执行；只有再显式
开启 `parallel_safe` 才可进入并行批次。Runtime 每次执行前重新发现当前 Tool，校验当前
Agent binding、参数 JSON Schema 和 schema hash，任一缺失、漂移或冲突均失败闭合。`side_effect + required` 只允许
Root WebSocket interaction 进入结构化确认：持久化 actor-bound action 和无 reasoning 的恢复快照，公开事件只返回
action 引用。approve/reject 在 tenant、actor、hash、version 和有效期校验后提交，再直接投递 TaskIQ。Child、schedule
和非 Root interaction 不支持审批；`executing` 状态中断后不得盲重试副作用 Tool。

子 Agent 由 runtime 创建为同一 Agent profile 下的 child interaction；它从持久化的 TaskBoard 合同生成
synthetic plan，不调用 Planner 模型。其 `kind`、能力提示、输出约束和
`timeout_seconds/max_tool_calls` 必须传入 child interaction 并受父级上限收紧。子 Agent 不得澄清或再次
派发子 Agent。最后一个 child 进入终态后，dispatcher 必须原子地将父 interaction 重新置为可领取并投递；
Planner-origin 父回合只接收已完成 TaskBoard 的结果上下文并进入 Final Renderer；Loop-origin Board 则恢复原始消息，
追加标准 `subagent_dispatch` Tool Result 后继续同一 Completion Loop，不得重新执行功能 Planner 或重复派发子任务。Root Planner
可以在入口选择 Subagent；普通 Root Tool Loop 也只在 `DelegationGate` 通过时看到 `subagent_dispatch`。同一 Root 最多
存在一块 TaskBoard；中途分派保存最多 64 KiB 的标准消息快照，移除 reasoning 和当前 dispatch call，超限则拒绝分派并
继续当前串行路径。Child 的 Tool Policy 仅允许只读自动能力，审批、写操作、schedule 和递归 dispatch 保留给 Parent。

`knowledge` Agent 不再调用独立的 `KnowledgeIntentAnalyzer`，也不接收服务端预塞的默认 Skill/MCP 候选目录。
worker 并发加载同一 tenant、Actor、Agent、P2P conversation 的近期 History 与受限 pinned Memory 后，将当前输入直接
交给统一 `AgentCompletionLoop`。平台规则与知识型政策合并为一条 system；Agent 业务策略仍可单独一条。因此简单回答
只需一次主模型调用；需要证据或能力时，由同一个模型回合按需调用工具，不存在额外的路由模型调用。同一意图的重复或近义
`knowledge_search` 由服务端拒绝（`KNOWLEDGE_SEARCH_REPEAT_BLOCKED`），避免无新查询理由的连环检索。

知识型 Loop 的服务端工具 allowlist 仍是确定性的。规则、流程、政策和内部事实需要证据时调用 `knowledge_search`；
明确要求查询实时业务对象或执行外部/内部业务流程时，使用完整请求调用 `capability_search(action=find_and_load)`
（非空 query：检索并加载顶层 Skill）。仅浏览候选时用 `find`（可空 query）；已有明确 ID 时用 `load`。
Skill 路径为 `find_and_load|find+load -> capability_execute`；MCP 继续受实时 binding、服务端 Tool Policy、参数 Schema、schema hash、
审批和入口能力约束。模型对工具的选择不授予任何权限，未暴露工具、越权 ID、错误参数和不允许的副作用都失败闭合。
`no_results` 与 `unavailable` 必须保持不同语义：前者表示当前授权范围内没有证据，后者只表示检索暂时不可用。

instruction-only Skill 成功 `load` 时，Runtime 在 tenant-private Interaction payload 中原子固定
`skill_id + skill_version`。若该回合通过 `ask_user` 进入 `waiting_user_input`，`interaction.steer` 恢复后必须先还原该
检查点和 Skill 指令，再继续同一 Skill；不得重新执行候选召回或切换其他 Skill。检查点版本不在 interaction 的不可变
profile snapshot 中时失败闭合，不能静默升级到当前发布版本。`ask_user(question)` 是缺少信息、选择或确认时的唯一等待
终态，并且仍只向可恢复的 Root WebSocket Loop 暴露。

活动 Skill 与普通 Tool Loop 都沿用 OpenAI-compatible 默认工具选择，不根据模型名称、thinking 字段或供应商切换
`tool_choice=required`。缺少信息时只能调用 `ask_user` 进入可恢复等待；`final_response` 是活动 Skill 的首选显式终点，
Provider 返回普通文本时仍须经过相同 Completion Gate。权限、Observation、TaskBoard 和工具回执均由 Runtime 裁决，
不能把模型文本、thinking 或 Tool Choice 当作执行成功证据。

`memory.search` 对非空关键词在当前可见记忆范围内融合 PostgreSQL FTS 和 dense-vector 候选，以
RRF 选择一个锚点；随后仅在该锚点同 Agent、同 scope 的时间序列中展开前后各五条记忆。全部候选和
展开记录均重新经过 PostgreSQL 可见性检查，工具结果携带受 token 上限约束的记忆正文；向量服务不可用
时安全降级为词法检索。未提供关键词时只浏览可见记忆，历史消息必须由显式 `sources=["message"]` 请求，
且不会参与记忆锚点或上下文展开。

Knowledge profile 的服务端 allowlist 包含 `memory`、`todo`、`time`、`math` 和 `knowledge_search`。
`knowledge_search` 只接收 query/limit，并在每次调用时重新经过 `KnowledgeRuntimePort` 的 tenant、Agent binding
和内容状态裁决，具体 PostgreSQL/向量实现不暴露给 Agent loop。默认 lexical 模式使用 PostgreSQL FTS；显式启用
hybrid 后，仅在当前 Agent 实时绑定的空间内取得 ANN 候选，以 RRF 合并 lexical/semantic 排名，并在返回正文前由
PostgreSQL 重新验证 Agent、空间、文档和版本状态。向量服务失败只回退 lexical，不能扩大候选权限。Knowledge Agent
还可使用管理员显式绑定的 instruction-only Skill，以及远程 HTTP/SSE MCP 中 schema hash 当前一致且服务端 Policy
已启用的 Tool。`read + automatic` 可自动执行；`approval=required` 只向 Root WebSocket 暴露并进入持久化审批，
非交互入口只发现自动只读 Tool。可执行或 MCP-backed Skill、stdio MCP、`script`、`schedule` 和 Child 审批均不在
知识 profile 中。能力只在统一 Loop 中按需发现，instruction-only Skill 的 `capability_execute` 只返回受限说明，绝不
启动 Bubblewrap 或声称发生了外部执行。远端 `readOnlyHint` 不能生成、覆盖或放宽服务端 Tool Policy。

管理台的召回验证分别检查 `capability_search` 的 Skill 与 MCP Tool 候选分支。Skill 分支按当前 Agent 类型、实时绑定和发布
状态形成候选集，对与运行时一致的 `name + description + SKILL.md` 文本评分，不加载指令或发现远端 MCP。MCP Tool 分支仅对
当前 Agent 绑定的启用服务做实时发现；知识型 Agent 继续排除 stdio，并只保留 schema hash 当前一致且服务端 Policy
已启用的 Tool。Root WebSocket 可看到 `read + automatic` 与 `approval=required`，其他入口只看到前者；远端
`readOnlyHint` 不能放宽该边界。该分支只发现和排序 Tool，不调用 Tool。

两个分支都复用运行时 BM25 与系统能力向量候选的 RRF 融合；向量健康时所有候选必须达到 Agent 持久化的最低相关度，避免
BM25 单字弱重合绕过评分门槛；向量异常时明确标记为 BM25 降级。同一查询的 embedding 按 `embedding_config_id` 去重，
多 Knowledge Space 在租户隔离会话内有界并行检索（默认并发 4）后再做跨 Space RRF。同一个阈值随 runtime profile
快照进入普通 Loop，并作用于 Skill 与 MCP Tool 的合并候选集。验证请求可临时覆盖阈值用于试算，只有单独、受
`agents.manage` 保护且有审计的 Agent 更新才会改变后续运行时。每个分支最多返回两个候选；验证不连接 LLM，也不能证明
Skill 或 MCP Tool 已成功执行或外部系统已发生变更。

runtime profile snapshot 只保存 `agent_type_key` 和已过滤 capability profile，不保存 knowledge binding 或空间 ID。
user/group knowledge grants 仅管理管理台内容可见性；匿名入口可读取已发布、允许匿名访问的知识 Agent 所绑定证据。

模型 transport 的瞬时错误只在总 timeout 内按配置重试。能力不存在、MCP capability 丢失或 MCP 执行
路由失败时，runtime 最多按 `agent_max_control_plane_replans` 次重新执行 Planner，并禁止再次请求已知不可用
的路由。工具轮数、总工具数或连续工具错误耗尽时，runtime 必须以无工具的最终渲染生成 `partial` 输出和预算
原因。直接回答、空参数 final_response 作答轮和 TaskBoard 汇总进入无 Tool Final Renderer，首个内容 delta 立即持久化，后续只做小窗口
微批。Root WebSocket Tool Loop 对内容 delta 投机公开为 durable `ai.output.delta`；同轮出现 tool_calls 或完成门
repair/partial 时 `ai.output.reset`。通过完成门后：已 live 流式的正文只发 completed（`deliver:live`，不为流式重写）；
带 content 的 `final_response` 一次候选；空参数 final_response 进入 Final Renderer 真流式；
`capability_lookup` 计划必须先获得工具 observation。无文本或缺少 observation 时，runtime 最多私下纠偏一次，
随后以固定、安全的 `partial` 结束，不使用模型草稿。`thinking_enabled` 的 Root WebSocket 可将 reasoning 经
`ai.thinking.*` 公开流式展示。

`ask_user(question)` 是唯一需要显式工具 intent 的等待输入终态，并且只向深度 0 的 Root WebSocket Agent Loop
暴露；schedule、subagent 和其他非交互入口不得进入 `waiting_user_input`。无 tool call 的完整普通文本通过运行时终态策略
后成为 live 或候选交付；`final_response()` 只兼容旧回合，并非正常工具。候选/live 交付前需写入 tenant-private
checkpoint；live 路径在 Provider 流结束后准备候选 checkpoint 供恢复，新普通候选一次发布完整文本，升级前旧
checkpoint 仍兼容其已保存 delta。Final Renderer 只发布确认后的实时内容 delta。
在首段可见后发生崩溃，恢复 worker 必须先发 `ai.output.reset` 并恢复候选或兼容最终渲染，绝不能重新执行已经完成的
工具。未来 IM adapter 对外投递只读取 durable output 事件：流式 adapter 可按 delta 编辑，非流式 adapter 仅在
completed/partial 终态投递一次完整内容。

模型与 MCP 账户密钥只允许作为认证加密后的密文存入数据库，API 与审计只暴露非敏感元数据；
独立加密主密钥保留在仓库外部署 secrets 中。生产启用进程内 runtime 时，
`ai.allowed_model_hosts` 必须是非空 allowlist，模型端点必须为 HTTPS。不得保存明文、回显密文，
也不得引入环境变量回退路径。

进程内运行由独立 runtime worker 领取持久化 input/profile snapshot；Web 进程不得启动 Agent
后台 task。worker 使用租约避免重复领取，并在终态事件提交时清除租约。会话历史只读取同一
tenant、actor、Agent 和 P2P conversation 的已持久化根 interaction 消息。不得将进程内内存状态
当作恢复依据。

## 错误映射伪代码

```pseudo
function mapHarnessError(error):
    if error is ValidationError:
        return apiError("AI_INPUT_VALIDATION_ERROR", 422)
    if error.code == "AI_POLICY_DENIED":
        return apiError("AI_POLICY_DENIED", 403)
    if error is ProviderUnavailable:
        return apiError("AI_PROVIDER_UNAVAILABLE", 503)
    return apiError("AI_INTERNAL_ERROR", 500)
```

## 必须测试

- WebSocket adapter 能把文本消息转换为 `HarnessRequest`，且不得把渠道私有配置传给 Agent runtime。
- 幂等键重复提交不会重复执行模型调用。
- provider 异常能映射为稳定错误码。
- 同一 P2P conversation 的持久化消息会回放，其他 actor、Agent 或 conversation 的消息不会回放。
- 历史消息必须按 interaction 聚合为连续回合，并在 token 预算不足时优先保留最新回合，不得跳过较新的回合去拼接旧消息。
- 知识意图分析只接收近期会话回合和当前问题且不传入工具；首轮召回必须以合法的 `knowledge_search` tool result
  插入当前用户问题之前，并分别覆盖 `ok`、`no_results` 和 `unavailable` 的回答边界。
- Skill/MCP sandbox、TaskBoard 来源证明、memory 确认和 schedule 来源证明均有失败闭合测试。
- Agent Loop 澄清、未授权工具拒绝、capability 重复熔断、纯工具并行、observation 脱敏压缩、lease fencing、
  todo/time/math/script 的输入和沙箱边界均有测试。
- 子 Agent synthetic plan、TaskBoard 预算传播、瞬时模型重试、预算 `partial` 总结、连续工具错误、候选不泄露、
  候选 delta 恢复和缺少 observation 的 bounded repair 均有测试。
