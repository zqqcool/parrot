# AI Multi-Entry Interaction Standards

本目录定义 AI 多入口交互的通用工程标准，不描述具体产品流程。

适用场景：

- 同一个 AI 能力通过人工绑定的 IM 渠道接入，并为未来 HTTP、SSE、语音 adapter 保留统一 harness 边界。
- 不同输入入口需要独立交互体验。
- 后端需要复用同一套模型编排、工具调用、上下文处理、错误处理和观测能力。

## 文档结构

```text
docs/ai-interaction/
  README.md               # 标准总览
  architecture.md         # 分层架构标准
  frontend-entries.md     # 前端入口标准与伪代码
  backend-harness.md      # 后端统一 harness 标准与伪代码
  interaction-contract.md # 接口契约标准与伪代码
  runtime-operations-runbook.md # Parrot runtime 启动、恢复与联调
  agent-runtime-implementation-plan.md # 当前唯一 Agent Runtime 实施方案
  agent-runtime-refactor-checklist.md # 与实施方案一一对应的落地清单
  agent-runtime-performance-baseline.md # 真实端点阶段耗时与限制
  agent-runtime-pipeline-redesign.md # 外部实践与总体问题研究记录
  subagent-orchestration.md # Subagent 长期编排研究记录
  multi-capability-orchestration-design.md # Skill/MCP/Subagent 当前分 Slice 实施依据
  multi-capability-orchestration-checklist.md # 当前实施进度与验收清单
  tool-schema-standard.md # 内置 Agent Tool 参数 Schema 类型标准
  context-memory-contract.md # Context、History 与 Memory 长期契约研究记录
  openai-compatible-provider-contract.md # Provider 兼容性与长期合同研究记录
  hermes-style-tool-loop-completion-gate.md # Tool Loop Completion Gate 研究记录
```

Agent Runtime 已实施基线继续由 `agent-runtime-implementation-plan.md` 与
`agent-runtime-refactor-checklist.md` 记录；当前多能力改造的唯一实施依据是
`multi-capability-orchestration-design.md` 与配套 Checklist。每个 Slice 只有在代码、测试和稳定标准同步完成后才并入基线。
其他专题文件只保留调研、风险和后续演进方向，不能直接据其增加新的工作流、输出持久化或 Provider 能力平台。

## 标准原则

必须遵守：

- 渠道独立：每个渠道 adapter 只负责自身协议、账户配置和消息转换，不得把渠道私有字段泄漏给 Agent runtime。
- 编排内核统一：未来语音和当前文本不得在后端各自实现一套 AI 调用链路。
- 入口只做适配：入口层只负责输入采集、校验和格式转换。
- harness 只处理标准请求：harness 不关心录音控件、文本编辑器等 UI 细节。
- 契约稳定：入口类型、输入类型、事件类型、错误码必须稳定可版本化。

推荐方案：

- 前端按渠道拆模块，按共享能力抽公共层。
- 后端按 `websocket route -> channel adapter -> interaction harness` 分层。
- 当前 WebSocket 渠道将消息直接转换为标准请求进入 harness；创建、事件、取消和追问均在同一连接内完成。

临时方案：

- 当前只支持人工创建并绑定的 WebSocket 渠道；不存在默认浏览器渠道。
- HTTP 管理 API 仅配置渠道和绑定，绝不承载 IM 消息；HTTP/SSE transport 暂未启用。
- 必须预留 `entry_type`、`input_type`、`channel_id`、`idempotency_key` 等字段。

不推荐方案：

- 前端把语音和文本入口写进同一个大组件。
- 后端在语音接口和文本接口中分别调用模型。
- 用前端传入字段决定敏感权限、模型策略或安全策略。
