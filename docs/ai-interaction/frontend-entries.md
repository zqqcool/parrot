# Frontend Entry Standard

## 目录标准

当前只开放人工绑定的 WebSocket 渠道。以下 HTTP、SSE、语音入口目录、状态机和伪代码是未来启用时的隔离模板，
不是当前可访问的功能或路由。

推荐按入口和共享能力拆分：

```text
src/
  features/
    ai-voice-entry/
      components/
      hooks/
      model/
      api.ts
    im-websocket/
      components/
      hooks/
      model/
      api.ts
    ai-shared/
      components/
      hooks/
      model/
      event-client.ts
      errors.ts
```

约束：

- `ai-voice-entry` 只能依赖 `ai-shared`，不得依赖 `ai-text-entry`。
- `im-websocket` 只能依赖 `ai-shared`，不得依赖未来 transport 的私有状态。
- `ai-shared` 不得包含麦克风、录音、文本编辑器等入口私有状态。

## 入口状态机标准

语音入口状态机：

```text
idle -> requesting_permission -> recording -> preparing_input -> submitting -> streaming -> completed
recording -> paused -> recording
recording -> cancelled
submitting -> failed
streaming -> failed
```

WebSocket 渠道状态机：

```text
disconnected -> connecting -> ready -> submitting -> streaming -> completed
ready -> submitting
streaming -> reconnecting -> replaying -> streaming
submitting -> failed
```

## 未来语音入口伪代码

```pseudo
state = "idle"

async function startVoiceInput():
    state = "requesting_permission"
    permission = await requestMicrophonePermission()
    if permission.denied:
        state = "failed"
        showError("MICROPHONE_PERMISSION_DENIED")
        return

    state = "recording"
    recorder.start()

async function submitVoiceInput():
    state = "preparing_input"
    audio = await recorder.stop()
    validateAudio(audio)

    state = "submitting"
    // Voice is a future IM adapter.  It must define its own normalized
    // channel command and receive output on that same channel; it does not
    // reuse a public HTTP interaction endpoint or an event_stream_url.
    await voiceChannel.send({ type: "interaction.create", data: { audio: audio } })

    state = "streaming"
```

## WebSocket 渠道伪代码

公开 Agent 详情页先加载该 Agent 的可测试渠道，再由用户显式选择一个渠道进入测试页；Agent slug 不得被当作
`channelKey`，也不得在多个绑定渠道中自动选择一个。

```pseudo
state = "idle"

function onTextChange(value):
    state = "editing"
    draft.text = value

function submitChannelMessage():
    state = "validating"
    validateText(draft.text)

    state = "submitting"
    socket.send({ type: "interaction.create", message_id: newId(), data: { text: draft.text } })
    state = "streaming"
```

## 共享事件处理伪代码

```pseudo
function connectChannel(channelKey):
    eventClient.connect(`/api/v1/im/ws/${channelKey}`, "parrot.im.v1")

    eventClient.on("ai.thinking.delta", event => {
        messageStore.appendThinking(event.interaction_id, event.data.delta)
    })

    eventClient.on("ai.thinking.completed", event => {
        messageStore.completeThinking(event.interaction_id)
    })

    eventClient.on("ai.output.delta", event => {
        messageStore.appendDelta(event.data.delta)
    })

    eventClient.on("ai.output.reset", event => {
        messageStore.clearOutput(event.data.output_id)
    })

    eventClient.on("ai.output.completed", event => {
        messageStore.complete(event.data.output_id)
        state = "completed"
    })

    eventClient.on("ai.output.failed", event => {
        messageStore.completeWithFailure(event.data.output_id, event.data.message)
        renderPersistentFailureNotice()
        state = "failed"
    })
```

`ai.output.failed` 是已持久化的运行终态，不得只显示会自动消失的 toast。公开页面必须使用后端提供的安全消息完成
当前 Assistant 消息，并保留明确的失败状态，断线重放后结果一致。传输层 `error` 仍可使用 toast，因为它不代表
一个已经建立的模型运行终态。Provider 原始错误、请求体、Reasoning 和工具事件不得进入公开消息。

## 不推荐实现

不推荐：

```pseudo
function submit():
    if mode == "voice":
        handleRecorder()
        callModelApi()
    else:
        handleTextEditor()
        callAnotherModelApi()
```

问题：

- UI 状态和模型调用耦合。
- 语音与文本容易产生两套错误处理。
- 后端策略无法统一治理。

## 管理端运营页面

后台运营能力按领域拆页，不得重新建立一个 Skyler 子控制台：

```text
features/admin/
  RunsPage.tsx       # Run 列表、事件时间线、实时输出
  MemoryPage.tsx     # 结构化记忆生命周期
  SchedulesPage.tsx  # 触发定义与执行历史
```

- 三个页面属于“智能体”导航分组，与 Agent、LLM、Skill、MCP 共享租户上下文。
- 页面通过 `shared/api` 调用 OpenAPI 对应接口；不得直接 `fetch`。
- Run 详情先读取持久化事件，再订阅管理端 WebSocket；按 `event_id` 去重、按
  `sequence` 排序，并在断线后使用最后 sequence 恢复。
- Run 诊断画布必须合并普通运行事件与管理端诊断追踪：按真实发生时间展示入口、规划、每次
  模型请求的元数据、Skill/MCP/工具调用元数据、最终输出和终态。诊断只显示阶段、次数、模型标识、
  数量、角色、工具名、`tool_choice`、状态和稳定错误码；默认及生产环境不持久化完整 messages、模型正文、工具定义、
  参数和 observation。仅 local 环境可通过显式诊断开关保存带 TTL 的 Provider 请求与响应快照，且不保存 Reasoning；
  这些内容绝不进入访客 WebSocket 或公开事件载荷。
- WebSocket 渠道创建、绑定、启停必须展示 loading、成功后的最新状态以及稳定错误；渠道页面必须明确展示可复制的 WSS 地址。
- 定时任务的执行记录必须显示关联 Run ID，使用户能回到运行进度继续排查。
