# AI Multi-Entry Architecture Standard

## 分层标准

标准架构必须分为四层：

```text
entry layer
  websocket channel

adapter layer
  websocket adapter

harness layer
  validation
  policy
  context
  model orchestration
  tool orchestration
  streaming
  persistence hooks
  observability hooks

contract layer
  request schema
  response schema
  event schema
  error schema
```

## 层职责

### Entry Layer

职责：

- 管理用户输入交互。
- 处理入口本地状态。
- 做低成本、可即时反馈的输入校验。
- 在所属协议连接内发送或接收消息。

禁止：

- 实现模型调用。
- 拼装后端内部 prompt。
- 执行权限最终裁决。
- 复用另一入口的私有状态。

### Adapter Layer

职责：

- 将入口请求转换为统一 `HarnessRequest`。
- 处理入口特有预处理。
- 补齐 `entry_type` 和 `input_type`。
- 屏蔽输入媒介差异。

禁止：

- 直接调用模型。
- 实现工具编排。
- 绕过 harness 写最终 AI 响应。

### Harness Layer

职责：

- 接收统一请求。
- 执行统一校验、策略、上下文、模型、工具、流式输出、错误映射和观测。
- 返回统一结果或事件流。

禁止：

- 依赖 UI 状态。
- 依赖具体录音、编辑器或上传组件。
- 为某个入口硬编码分支流程。

### Contract Layer

职责：

- 定义稳定请求、响应、事件和错误结构。
- 约束版本兼容性。
- 为前后端生成类型或测试夹具提供依据。

## 标准流程伪代码

```pseudo
function handleEntryRequest(rawRequest, entryType):
    adapter = adapterRegistry.get(entryType)
    if adapter is null:
        return error("ENTRY_TYPE_UNSUPPORTED")

    harnessRequest = adapter.toHarnessRequest(rawRequest)
    return aiHarness.run(harnessRequest)
```

```pseudo
function runHarness(request):
    validate(request)
    principal = authenticate(request)
    authorize(principal, request)
    applyRateLimit(principal, request)

    normalizedInput = normalizeInput(request)
    context = buildContext(principal, normalizedInput)
    plan = createExecutionPlan(context, request.options)

    resultStream = executeModel(plan)
    return streamAndPersist(resultStream, request)
```

## 设计取舍

推荐方案：

- 入口拆分，harness 合并。
- 入口层保留交互差异，后端编排保持一致。

当前方案可以工作的原因：

- 语音和文本的采集方式不同，入口拆分能降低 UI 状态复杂度。
- 二者进入 AI 编排后的核心流程高度一致，统一 harness 能保证策略和观测一致。

隐患：

- 如果入口不拆，前端状态机会膨胀，取消、重试、恢复和错误处理会相互影响。
- 如果 harness 不统一，模型策略、工具调用、安全控制、成本控制会出现分叉。

## 运行与运营能力

AI 执行产生的运行状态、记忆和定时任务属于 Parrot 内部领域模块，不是独立的 Skyler
控制台。三者必须复用 Parrot 的身份、租户、审计、请求 ID 和 API 契约：

```text
websocket / schedule entry
            |
            v
     interactions (Run source of truth)
        |       |
        |       +--> durable interaction_events --> HTTP recovery
        |                                    \----> WebSocket live stream
        |
        +--> runs (read model, no duplicate Run table)

memory --------> PostgreSQL authorization source + TaskIQ-delivered vector operation
schedules -----> TaskIQ scheduler -> interaction submission
```

约束：

- `interactions` 是 Run 与事件的事实源；`runs` 只提供后台查询视图，不复制执行状态。
- `memory` 的结构化记录与会话消息均受 PostgreSQL 租户隔离保护；向量检索只返回候选，
  必须再次按关系库可见性过滤。索引由 TaskIQ task 处理；记录只保存状态、版本与幂等边界。
- `schedules` 只拥有任务定义与触发历史，实际执行必须进入统一 interaction harness。
- TaskIQ scheduler 是独立进程，不得在 Web 进程中启动后台循环；每次 cron 的 IANA 时区
  下一次触发时间由领域函数计算，再作为一次性绝对时间任务登记，避免固定偏移破坏夏令时。
- 管理端实时进度复用 `parrot.im.v1` 事件语义，但使用 Web session 和
  `interactions.read.any` 权限，并且只允许订阅，不提供越权控制命令。
- 当前仅开放人工绑定的 WebSocket IM 渠道。WebSocket 创建 interaction、回放持久化事件、取消和追问；HTTP
  仅用于管理配置。未来 HTTP、SSE 或语音必须作为独立 adapter 接入同一 harness，不能污染 WebSocket 渠道状态。
