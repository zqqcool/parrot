# Test Skill packages

`beijing-to-shanghai-promotion/` 保留原有路径以兼容现有测试脚本，但内容已改为“用户信息收集”
说明型 Skill。它要求 Agent 按最小必要原则收集服务登记信息，并在用户明确确认后调用已绑定的
本地测试 MCP 工具 `create_ticket`。

该包没有 `manifest.json`，导入后是说明型 Skill，不会启动 `main.py` 或 Skill 沙箱。旧的入口脚本
已移除，避免与当前业务测试语义冲突。

## 联调前提

- 启动 `mcp-api-echo-demo`，并配置 Streamable HTTP 地址为 `http://127.0.0.1:8765/mcp`。
- 将该 MCP 和发布后的 Skill 同时绑定到功能型 Agent。知识型 Agent 会过滤写入型 MCP 工具，不能创建工单。
- `create_ticket` 是无外部持久化的测试工具：它需要完整的最小必要信息和用户确认，返回 `TEST-TICKET-*` 标识。

## 使用流程

1. 上传 `beijing-to-shanghai-promotion.zip`，发布说明型 Skill。
2. 将 Skill 与本地测试 MCP 关联到同一个功能型 Agent。
3. 发送：`我想预约产品演示，请联系我。`
4. Agent 补充称呼、联系方式、城市和业务需求；预约场景再补充期望时间。
5. 用户回复明确确认，例如：`确认创建测试工单。`
6. Agent 发现并调用 `create_ticket`，仅在返回成功后告知 `TEST-TICKET-*` 工单编号。

这是联调样例，不可用于真实工单、用户档案或外部服务提交。真实系统需要由工单服务端校验用户确认、权限、
幂等键和审计上下文，不能仅依赖模型传入的 `confirmed` 字段。
