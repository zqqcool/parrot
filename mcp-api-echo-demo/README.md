# MCP and HTTP Test Demo

一个独立的、无状态的本地测试服务：不读取 Parrot 配置、不连接数据库、不挂到正式
应用。它提供一个回显工具和一个“创建测试工单”工具；后者不向任何外部系统写入数据。

## 启动

```bash
cd mcp-api-echo-demo
uv sync --extra dev
uv run mcp-api-echo-demo
```

没有 `uv` 时，使用 Python 3.13+：

```bash
python3.13 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/mcp-api-echo-demo
```

默认只监听 `127.0.0.1:8765`；可用 `--host`、`--port` 修改。

| 协议                | 地址                                  | 行为                                  |
| ------------------- | ------------------------------------- | ------------------------------------- |
| HTTP API            | `POST http://127.0.0.1:8765/api/echo` | 打印并返回任意请求体。                |
| MCP Streamable HTTP | `http://127.0.0.1:8765/mcp`           | 暴露 `echo` 和 `create_ticket` 工具。 |

HTTP 调用示例：

```bash
curl -sS http://127.0.0.1:8765/api/echo \
  -H 'content-type: application/json' \
  -d '{"message":"hello from HTTP"}'
```

MCP 客户端把服务地址设置为 `http://127.0.0.1:8765/mcp`，发现工具后调用：

```json
{
  "name": "echo",
  "arguments": {
    "payload": { "message": "hello from MCP" }
  }
}
```

创建测试工单必须在用户明确确认后调用。它是写入型 MCP 工具，只能绑定到功能型 Agent；
知识型 Agent 只可发现和调用只读 MCP 工具。

```json
{
  "name": "create_ticket",
  "arguments": {
    "contact_name": "测试用户",
    "contact_method": "user@example.test",
    "city": "上海",
    "business_need": "预约产品演示",
    "requested_time": "周五上午",
    "confirmed": true
  }
}
```

工具会校验四项必填信息和 `confirmed: true`，仅返回无敏感字段的 `TEST-TICKET-*` 标识；不会保存、
转发或回显联系人信息。终端会打印每个 HTTP 请求（包括 MCP 协议消息）以及工具调用摘要。为避免误泄漏，
`Authorization`、Cookie 和常见 API Key 请求头会脱敏；该服务仍不应绑定到不受信任的网络，也不应用于敏感请求体。
