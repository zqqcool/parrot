# Agent Runtime 性能基线

> 状态：本地知识路径基线已建立；功能型 direct、单 Tool 与 Subagent 的真实端点对照待测试 Agent
> 日期：2026-07-20

## 1. 测量边界

本记录用于验证当前重构是否把额外延迟留在 Provider 之外，而不是用单次主观体验宣称“更快”。本轮环境为：

- 本地 Web、TaskIQ worker、scheduler、PostgreSQL 和 Redis；
- 匿名 WebSocket 知识型 Agent；
- OpenAI-compatible Chat Completions；
- Provider/model：`deepseek/deepseek-v4-flash`；
- 固定知识问题，每个样本使用独立匿名会话；
- 每轮 1 次预热、10 次计入样本；
- 三个灰度开关全部开启。

脚本从发送 `interaction.create` 后开始计时，不包含 WebSocket 建连。它只记录 Interaction ID、终态和耗时，
不打印或写入模型回答。脚本会创建持久化 Interaction 并产生真实 Provider 请求，因此必须显式传入
`--confirm-real-requests`。

## 2. 端到端结果

| 轮次 | Intent fallback | accepted p50/p95 | 首个公开 delta p50/p95 | completed p50/p95 |
| --- | ---: | ---: | ---: | ---: |
| 严格 JSON 解析 | 3/11 | 39.0/62.1 ms | 1.96/2.27 s | 5.36/5.99 s |
| 单 JSON fence 兼容后 | 0/11 | 25.8/40.0 ms | 2.35/2.93 s | 5.78/6.25 s |

两轮样本少、Provider 输出长度和生成调度不可固定，不能把轮次间的约 0.4 秒差异解释为代码性能变化。第二轮的
确定结论是：同一端点偶发的严格 `json` Markdown fence 不再导致知识 Intent fallback，且全部样本完成。

两轮知识 Evidence 均为 `degraded`：至少一个查询取得可用证据，同时存在无结果分支。该状态用于提示部分取证，
不代表请求失败，也不能与纯 `ok` 样本直接比较答案耗时。

## 3. Runtime 阶段结果

修复后的 11 次运行（含预热）由 management-only diagnostics 得到：

| 阶段 | p50 | p95 |
| --- | ---: | ---: |
| Runtime 开始到公开首段 | 2.24 s | 2.84 s |
| Runtime 开始到内容生成完成 | 5.70 s | 6.16 s |
| Provider 首内容到 durable 公开首段 | 15.6 ms | 20.1 ms |

因此当前知识路径的主要延迟来自 Intent 模型调用、知识取证和 Final Provider 生成，不是旧 Candidate delta 回放，
也不是事件持久化到公开通知。`run_completed` 在本轮前曾因终态事件提前释放 worker lease 而无法写入；现已改为
由 worker `finally` 在后终态诊断和 checkpoint 收尾完成后释放 lease。

## 4. 可重复命令

```bash
backend/.venv/bin/python scripts/benchmark_interaction_websocket.py \
  --url 'ws://127.0.0.1:8000/api/v1/im/ws/<channel-key>' \
  --origin 'http://127.0.0.1:5173' \
  --prompt '<固定且不含敏感数据的问题>' \
  --label '<小写基线标签>' \
  --samples 20 \
  --warmup 1 \
  --output /tmp/parrot-agent-runtime-benchmark.json \
  --confirm-real-requests
```

每次对比必须固定 Agent、模型配置、Prompt、知识版本、并发和部署资源。Provider/model 仅作为本次环境事实；
Runtime 仍只依赖项目定义的 OpenAI-compatible 最小合同，不根据模型名称分支业务行为。

## 5. 尚未关闭的发布项

以下项目没有足够事实，继续保留为待办：

1. 建立功能型测试 Agent，对 `agent_direct_rendering_enabled=true/false` 做同配置对照；
2. 固定一个成功的只读 Tool 样例，记录 Tool Loop 首段和总耗时；
3. 固定两个独立 Child 的 Subagent 样例，记录 Parent accepted、Child 并发和最终汇总；
4. 在 staging 以每条路径至少 30 个样本记录 p50/p95、错误率、fallback 率和 Token；
5. 灰度稳定且旧 checkpoint 过期后，才删除 Candidate 兼容恢复路径。

在这些条件完成前，本记录只能证明当前本地知识路径和 Provider→公开事件开销，不能证明所有 Agent 路径的生产
p50/p95 已达标。
