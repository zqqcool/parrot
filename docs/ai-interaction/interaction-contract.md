# Interaction Contract Standard

## Transport boundary

当前版本仅支持人工创建、人工绑定的 WebSocket IM 渠道：

```text
HTTP /api/v1/admin/tenants/{tenant_id}/im/channels       # 管理配置
HTTP /api/v1/admin/tenants/{tenant_id}/im/agent-bindings # 管理绑定
HTTP /api/v1/public/agents/{slug}/channels               # 公开测试入口发现
WSS  /api/v1/im/ws/{channel_key}                         # IM 全生命周期
WSS  /api/v1/im/admin/ws?protocol=parrot.im.v1           # 管理只读进度
```

没有默认浏览器渠道。`channel_key` 必须对应已启用、已绑定、且目标 Agent 可匿名访问的
WebSocket 渠道。HTTP 管理 API 不得创建、查询、恢复或控制访客 IM interaction；HTTP 和 SSE
transport 留待后续独立 adapter 实现。

公开 Agent 详情页通过渠道发现接口列出该 Agent 已绑定、已启用且可匿名访问的 WebSocket 渠道；用户必须显式选择
其中一个渠道后才进入 `/im/websocket/{channel_key}` 测试页。接口只返回渠道名称、类型和路由 key，不返回
Origin 白名单、账户配置或凭据；它不是默认浏览器渠道，也不得按 Agent slug 自动选择渠道。

OpenAPI 描述管理 API，AsyncAPI (`backend/asyncapi/asyncapi.yaml`) 描述 WebSocket 消息协议。

## Channel and binding records

每个渠道至少包含：`tenant_id`、`channel_type`、名称、不可猜测的 `public_key`、状态和渠道配置。管理端从
`GET /api/v1/admin/tenants/{tenant_id}/im/channel-types` 读取类型目录；当前只有 `websocket` 为可创建类型，
飞书、钉钉和企业微信必须保持禁用，直到其独立 adapter、凭据配置和测试完成。渠道凭证必须放入独立的
加密凭证表，禁止进入 `config_json`、事件或 Agent 输入。

每个渠道最多绑定一个 Agent；绑定、interaction 和入站投递都必须携带同一 `tenant_id`。入站幂等范围为：

```text
(channel_id, visitor_id, client_message_id)
```

不能只按渠道和客户端消息 ID 去重，否则可能把一个访客的 interaction 错误暴露给另一个访客。

## WebSocket handshake

客户端必须以 `parrot.im.v1` 子协议连接，并发送浏览器 `Origin`。服务端依次校验子协议、全局 Origin
策略、渠道精确 Origin、渠道状态、绑定状态和 Agent 发布/匿名访问状态。首次连接由服务端在握手响应中
设置 opaque HttpOnly visitor cookie；token 不得出现在 URL、命令或日志中。

## Envelope

```json
{
  "version": "1",
  "type": "interaction.create",
  "message_id": "msg_01J...",
  "request_id": "req_01J...",
  "interaction_id": null,
  "sequence": 0,
  "occurred_at": "2026-07-14T10:00:00Z",
  "data": { "text": "user input" }
}
```

客户端命令：

```text
interaction.create    # 在当前连接内创建 interaction；message_id 是入站幂等键
interaction.subscribe # 以 interaction_id + 最后 sequence 断线续传
interaction.ack
interaction.cancel
interaction.steer
interaction.approve  # 仅处理当前 interaction 返回的结构化 action 引用
interaction.reject
ping
```

服务端事件：

```text
connection.ready
interaction.accepted
pong
error
ai.*                  # 从持久化 interaction_events 重放或实时投递
```

`interaction.create` 成功后先返回 `interaction.accepted`，随后在同一连接内投递持久化事件。Redis
只提供“已提交事件”通知；服务端总是按 sequence 从 PostgreSQL 读取 payload。公开 WebSocket 采用默认拒绝的
可见性策略：只投递 `ai.output.delta`、`ai.output.reset`（历史兼容）、`ai.output.completed`、
`ai.output.cancelled`、`ai.output.failed`，以及 Root WebSocket 在 `thinking_enabled` 时的
`ai.thinking.delta` / `ai.thinking.completed`。`ai.input.*`、`ai.agent.*`、`ai.tool.*`、`ai.knowledge.*`、
`ai.subagent.*` 以及任何未显式允许的新事件都不得投递给访客。即使事件被过滤，服务端仍推进 sequence；重连时
`subscribe` 先补发遗漏的公开事件，再进入实时订阅，因此客户端必须按 `message_id` 去重。

WebSocket `error` 与 `ai.output.failed` 事件的 `data` 必须同时包含稳定的 `code` 与后端错误目录生成的中文
`message`。客户端只能在 `message` 提示中展示该字段，不得直接展示错误码或服务端内部异常文本；若事件损坏或缺少
`message`，使用固定的中文兜底提示。

## Management Run request snapshots

`GET /api/v1/admin/tenants/{tenant_id}/runs/{run_id}/diagnostic-traces` is a tenant-scoped,
management-only API protected by `interactions.read.any`; it is never part of the public WebSocket
event stream. A `model.request` trace always carries phase, attempt, provider/model identity, message
count, roles and tool names. Only when `app.environment` is `dev` or `sit` and
`ai.debug_capture_prompts = true`, it additionally carries this exact provider-ready prompt contract:

```json
{
  "request_snapshot": {
    "format": "openai-compatible.chat-completions.v1",
    "messages": [{ "role": "system", "content": "..." }],
    "tools": [{ "type": "function", "function": { "name": "..." } }]
  }
}
```

The snapshot excludes credentials, authorization values, cookies and provider endpoints, inherits
transcript expiry, and is unavailable to historical or non-local runs. Frontend Run views must render
only `request_snapshot` as the full prompt; they must not infer it from metadata or public events.

`runtime.milestone` 也是 management-only trace。当前稳定名称为
`queue_wait`、`provider_first_content_delta`、`public_first_delta`、`model_turn_completed` 和
`run_completed`。`elapsed_ms` 均从 worker 开始执行该 interaction 计时；`queue_wait` 额外携带
`queue_wait_ms`（dispatch 写入的 `runtime_enqueued_at` 到 claim/execute 的间隔）。`model_turn_completed`
携带 `turn`、`duration_ms`、`tool_call_count` 与 `content_characters`。该 trace 只携带阶段、耗时和必要的
关联数值，不得携带 prompt、模型文本或 Tool 参数。`model.response` 在端点返回 usage 时可含
`prompt_tokens` / `completion_tokens` / `total_tokens` / `cached_tokens`（仅管理诊断）。`tool.result` 可含
`duration_ms`，知识检索还可含 `embed_duration_ms` / `space_count` / `retrieval_method`。

模型工具回合与用户可见输出严格分离。模型不得把答案放入终态工具参数：

- `ask_user(question)` 是唯一的澄清终态；它只向可恢复的 Root WebSocket Agent Loop 暴露，必须单独调用，运行时以
  该问题写入 `ai.output.completed(runtime_status=waiting_user_input)`。知识型 Agent 已直接进入该 Root Loop，因此可以
  使用 `ask_user`；schedule 和 subagent 不得发起用户澄清。
- 功能型 `direct_answer`、已完成 TaskBoard 汇总直接进入无 Tool 的 Final Renderer；该阶段的首个
  非空内容 delta 可以成为公开 delta，因为 Runtime 已经在进入阶段前确定不会继续 Agent Loop。
- Root WebSocket Agent Loop 对 Provider 内容 delta 采用投机公开：边收边写 durable `ai.output.delta`。若同轮随后
  出现 tool_calls，或完成门要求 repair/partial，则发送同 `output_id` 的 `ai.output.reset` 并撤回草稿。通过完成门后
  只再发 `ai.output.completed`（不再为流式二次生成，也不回放假切片）。尚缺 capability Observation 的
  `capability_lookup` 计划不得投机公开正文，避免闪现未取证草稿。
- 交付分流：完成门通过后，若本轮已 live 流式写出正文 → `deliver:live`（仅 completed + 候选 checkpoint 供恢复）；
  空参数 `final_response` → Final Renderer 真流式；带 content 的 `final_response`（工具参数短答）→ 一次候选交付。
  **禁止**为打字机效果再调模型重写已有正文。
- `final_response()` 空参数表示进入唯一作答轮；已输出正文时不应再调用。可选 `content` 仅作短答兼容。

工具名称、工具参数和工具结果不能发布。在 Root WebSocket 且 Agent LLM `thinking_enabled=true` 时，
`reasoning_content` / reasoning delta 可经 `ai.thinking.*` 向访客流式展示；thinking 关闭或非 Root 时 reasoning
仍仅私有回传 Provider。Final Renderer 与 Agent Loop 均将首个非空内容 delta 立即写为 durable
`ai.output.delta`，后续只允许按 50 ms 或 96 字符微批。终态 `ai.output.completed` 同时携带完整 `content`，
用于断线后客户端收敛；知识型回答还可附带结构化 `citations[]`（标题/锚点）与 `media[]`（interaction
已投放的 primary 配图引用，不含对象存储密钥）。旧客户端可忽略新字段仍只渲染文本。客户端以 `output_id`
聚合答案、以 `thinking_id` 聚合思考，并以 `message_id` 去重。访客下载配图须走
`GET /api/v1/im/interactions/{interaction_id}/knowledge/media/{asset_id}/content`，且仅当该
`asset_id` 已出现在本 interaction 的 `ai.output.completed.media` 时放行。

最终渲染或候选交付开始前必须持久化 tenant-private checkpoint。新普通候选 checkpoint 保存完整文本、稳定
`output_id`、终态状态和过期时间，并一次交付；升级前已经持久化的多 delta candidate 仍可按原数据恢复。Final
Renderer checkpoint 保存可重新渲染的受限消息和可见状态。租约恢复发现可见但未完成的 checkpoint 时，先写
`ai.output.reset`，再以同一 `output_id` 恢复候选或重新执行 Final Renderer；恢复不得重新执行此前 Agent Loop 或工具。
`capability_lookup` 路径在至少获得一次成功且相关的 Tool Observation 前不得交付候选；无文本或缺少 Observation 时，
最多私下纠偏一次，之后输出运行时生成的安全 `partial`，不发布草稿。

需要副作用的 MCP Tool 只能在服务端 Tool Policy 标记为 `approval=required` 时进入 Root WebSocket 的结构化确认。
Runtime 在执行前持久化 actor-bound action，公开 `ai.output.completed(runtime_status=waiting_user_action)` 只包含
`action_id`、`action_hash`、`version` 和 `approve/reject` 选项，不能包含 Tool 名、Capability ID、参数或凭据。客户端
随后发送 `interaction.approve` 或 `interaction.reject`，并原样带回这三个引用字段；服务端校验 tenant、actor、状态、
hash、version 和 15 分钟有效期，提交决定后直接投递 TaskIQ。schedule、Child/Subagent 和非 Root interaction 不支持
审批，必须拒绝该 Tool。执行开始后若 worker 状态不确定，Runtime 不得自动重试副作用操作，只能以 `partial` 告知结果
不确定。

## Runtime and Agent boundary

WebSocket adapter 只生成标准 `InteractionSubmission(entry_type="websocket", input_type="text")`，并写入
`im_channel_id`、`im_agent_binding_id` 以便审计和所有权检查。Agent runtime 只接收标准化文本、actor、
conversation 与已解析的 Agent runtime ID；它不得接收 Origin、Bot 凭证、飞书字段或其他渠道私有配置。

当前 Agent 的用户可见最终输出由私有终态候选或兼容最终渲染持久化为 `ai.output.*` 事件；WebSocket adapter
只投递这些公开输出事件，不能把 Agent 执行过程当作用户消息。未来若需要主动推送或第三方机器人回调，
必须以 terminal-only delivery intent 消费已持久化的 `ai.output.completed`/失败终态，写独立出站记录和转换目标
payload；支持流式编辑的 adapter 可以按 durable delta 更新，非流式 adapter 只能在终态一次性投递完整 `content`。
飞书等 adapter 只能在 IM 模块内增加账户配置、出站状态机和转换，不得修改 Agent tool schema 或从 runtime trace
读取中间内容。

## Errors and compatibility

稳定错误码至少包括：

```text
AI_INPUT_VALIDATION_ERROR
AI_INTERACTION_NOT_FOUND
AI_PROVIDER_UNAVAILABLE
IM_PROTOCOL_INVALID
IM_CHANNEL_NOT_FOUND
IM_CHANNEL_NOT_BOUND
IM_CHANNEL_AGENT_UNAVAILABLE
RATE_LIMITED
```

可以向 `data` 增加字段；不得改变 `version`、事件 `type` 或已有错误码语义。新增 HTTP/SSE/飞书等渠道时
必须新增独立 adapter、账户配置 schema、测试和 AsyncAPI/供应商契约，不能在 WebSocket route 或 Agent
runtime 内堆叠条件分支。
