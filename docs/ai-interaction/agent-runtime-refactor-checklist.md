# Agent Runtime 落地 Checklist

> 状态：代码实施完成，待测试环境性能对比与灰度观察
> 唯一实施依据：[Agent Runtime 可落地实施方案](agent-runtime-implementation-plan.md)
> 日期：2026-07-19

> 范围说明：本清单记录统一 Loop 的既有基线。SkillContext、结果型 Subagent、完成证据与安全并行只在
> [多能力编排 Checklist](multi-capability-orchestration-checklist.md) 按独立 Slice 跟踪；不得从本文件的历史条目反推新合同。

## 1. 使用规则

- `[x]`：当前代码已经存在且已核对。
- `[-]`：已有基础，但未形成目标闭环。
- `[ ]`：尚未实施。
- `[!]`：正确性或上线阻断项，必须优先关闭。
- 只有代码、自动化测试和必要文档均完成后，才允许把条目标为 `[x]`。
- 每个 PR 只完成一个 Slice；不得顺手引入“暂不实施”列表中的平台化抽象。

## 2. 已有基线

| ID | 状态 | 能力 | 代码事实 |
| --- | --- | --- | --- |
| BASE-01 | `[x]` | 功能型 Root 使用 Planner | `turn_planning.py::plan_turn()` |
| BASE-02 | `[x]` | 知识型直接结合 History 与 pinned Memory 进入共享 Loop | `knowledge_execution.py` + `prompt_composer.py` |
| BASE-03 | `[x]` | 会话消息持久化时区时间 | `ConversationMessage` 继承 `TimestampMixin` |
| BASE-04 | `[x]` | Finalization 可恢复 | `FinalResponseRenderer` + `SqlFinalizationCheckpointStore` |
| BASE-05 | `[x]` | 公开事件先提交再通知 | `InteractionEventStore.append()` |
| BASE-06 | `[x]` | 入口 Subagent 有持久化执行链 | TaskBoard + Child Interaction + TaskIQ |
| BASE-07 | `[x]` | 功能型 Tool Loop 可执行结构化 Tool Call | `AgentCompletionLoop` + `RuntimeToolExecutor` |
| BASE-08 | `[x]` | Provider 最小结构化响应 | content/tool call/finish reason/private reasoning 均有合同测试 |

## 3. Slice 0：性能反馈环

目标：先建立能阻止性能回退的信号，不凭流程图承诺速度。

| ID | 状态 | 待执行项 | 完成条件 |
| --- | --- | --- | --- |
| PERF-01 | `[-]` | 建立四路径 benchmark | 已覆盖调用数、惰性分支和首 delta 闸门；真实总时长 p50/p95 待测试环境 |
| PERF-02 | `[x]` | 记录当前模型调用基线 | direct=2、knowledge 短答/工具后有正文=1→2、空参数 final 作答=再+1、入口 Subagent=1 |
| PERF-03 | `[x]` | 验证条件分支惰性 | direct/knowledge 均未触发 MCP 发现或执行，direct 未 dispatch Child |
| PERF-04 | `[x]` | Fake Provider 确定性测试 | 异步闸门证明 Final Renderer 首个 Provider 内容 delta 已公开，尾部仍被阻塞 |
| PERF-05 | `[-]` | 测试环境 p50/p95 对比 | 本地知识路径已有真实基线；优化前及其余三路径待 staging 对照 |

验收证据：一条可在 CI 运行的确定性命令，以及一份测试环境真实端点对比结果。

当前确定性命令：

```bash
cd backend
./.venv/bin/pytest -q tests/test_agent_runtime_performance_contract.py
```

2026-07-19 实施结果：`6 passed`。direct 路径在 Provider 首个非空内容 delta 后立即产生首个 durable 公开 delta，
并且未增加模型调用次数。

## 4. Slice A：正确性基线

目标：在优化速度前，先阻止错误文本提前结束任务。

| ID | 状态 | 待执行项 | 完成条件 |
| --- | --- | --- | --- |
| A-01 | `[x]` | Planner 失败改为 fail-closed | Provider/解析/非法 action 不再静默返回 `direct_answer`；有单测 |
| A-19 | `[x]` | Planner 不直接澄清 | `agent_loop` 承接后续判断；旧 `clarify` 兼容映射到 Loop，只有 `ask_user` 可等待 |
| A-02 | `[x]` | Provider 解析 `finish_reason` | 正常结束、Tool、截断和未知值合同测试通过 |
| A-03 | `[x]` | 保留可选私有 reasoning/provider state | 不产生公开事件；需要回传的端点可完成 Tool Loop |
| A-04 | `[x]` | 增加 `ToolObservation` | 成功、业务失败、权限失败、超时和未知 Tool 可区分 |
| A-05 | `[x]` | 完成门使用成功 Observation | `capability_lookup` 不能由任意 Tool 调用次数满足 |
| A-06 | `[x]` | 早期普通文本最多修复一次 | 修复失败进入 partial/failed，不公开早期文本 |
| A-07 | `[x]` | 新增最小服务端 Tool Policy | 未知/冲突 fail closed；只有明确 read 可自动执行 |
| A-08 | `[x]` | 持久化单个 PendingToolAction | 参数/hash/policy/expiry/resume messages 写入 Interaction payload |
| A-09 | `[x]` | 增加结构化 approve/reject | 校验 tenant/actor/action/hash/version；commit 后直接 TaskIQ dispatch |
| A-10 | `[x]` | 写操作不确定结果禁止盲重试 | executing worker 中断后为 uncertain；无幂等回执不重试 |
| A-11 | `[x]` | 不支持 action 的入口拒绝需审批 Tool | schedule/subagent/非 Root 不进入结构化审批 |
| A-12 | `[x]` | pending action 公开摘要 fail-closed | 公开事件不泄露 Tool 名、Capability ID、原始参数或凭据 |
| A-13 | `[x]` | History 保留原生角色和发生时间 | user/assistant 原生消息携带服务端生成的 ISO 8601 历史 header；当前请求独立且优先 |
| A-14 | `[x]` | History 与必要 Memory 并发加载 | 顺序稳定，异常行为与当前合同一致 |
| A-15 | `[x]` | 动态 TaskBoard 降为 reference 数据 | 不再注入高优先级 system 指令 |
| A-16 | `[x]` | 修复 Memory reference 重复包裹 | Prompt 快照测试无双层 wrapper |
| A-17 | `[x]` | waiting 补充信息恢复闭环 | steer 提交后清除旧 lease 并直接 TaskIQ dispatch；前端保持处理中；有竞争窗口回归测试 |
| A-18 | `[x]` | 同一 Interaction 多轮会话账本 | sequence 保存 waiting/steer/终态，历史按轮配对；迁移回填已有事件 |
| A-20 | `[x]` | Agent 能力最低相关度 | profile 快照统一约束 Skill/MCP 混合候选；仅向量异常时 BM25 降级；管理台可分别验证并显式应用 |
| A-21 | `[x]` | 显式 Planner 服从 Observation 门 | 功能型 Planner 要求能力时至少产生一次工具 Observation；候选非空本身不构成必执行合同 |
| A-22 | `[x]` | Durable 首次领取无占位租约竞态 | 本地 accepted 只保存 execution ID；TaskIQ Worker 首次 claim 才持有 lease |

验收证据：Planner、terminal policy、provider stream、history/prompt 的单元和服务测试全部通过。

## 5. Slice B：最终输出快路径

目标：复用现有 durable Finalization，删除常见路径的完整缓存和 delta 回放。

| ID | 状态 | 待执行项 | 完成条件 |
| --- | --- | --- | --- |
| B-01 | `[x]` | 功能型 `direct_answer` 直接进入 Renderer | 不再经过 CandidatePublisher；Planner 仍保留 |
| B-02 | `[x]` | 知识型合成直接进入 Renderer | tools 为空，Reasoning/Tool 过程不可见 |
| B-03 | `[x]` | completed TaskBoard 直接进入 Renderer | Child 结果一次合成，Parent 不重跑 Planner |
| B-04 | `[x]` | Renderer 内实现小型 delta 微批 | 首个非空 delta 立即提交；后续按 50 ms/96 字符微批 |
| B-05 | `[x]` | 普通合法 end-turn 一次发布完整文本 | 不逐 delta 回放，不伪装模型实时流 |
| B-06 | `[x]` | 保留旧 Candidate 恢复兼容 | 升级前未完成 Interaction 可继续恢复 |
| B-07 | `[x]` | 恢复与幂等测试 | Candidate/Renderer 中断恢复不重跑工具与 Agent Loop |
| B-08 | `[x]` | 记录关键阶段时间 | management trace 可比较 provider/public first delta 和总时长 |

验收证据：direct/knowledge/TaskBoard 三条集成测试及进程中断恢复测试通过；相同输入不再出现回放阶段。

## 6. Slice C：知识型统一 Loop

目标：删除前置 Interpreter 和默认候选注入，让主模型按需调用受服务端约束的知识与能力工具。

| ID | 状态 | 待执行项 | 完成条件 |
| --- | --- | --- | --- |
| C-01 | `[x]` | 删除前置 Knowledge Interpreter | 知识请求不再产生 route JSON 模型调用 |
| C-02 | `[x]` | 删除默认候选目录 | Prompt 不含 `knowledge_capability_candidates` |
| C-03 | `[x]` | 共享 Root Agent Loop | 首轮同时暴露受限知识、Memory、能力和 `ask_user` 工具 |
| C-04 | `[x]` | 知识按需检索 | `knowledge_search` 每次重新校验 tenant、Agent binding 和内容状态 |
| C-05 | `[x]` | 能力按需发现 | 业务请求由主模型调用 `capability_search(find)`，不预取 Skill |
| C-06 | `[x]` | instruction-only Skill 边界 | 只允许已发布、已绑定说明，不运行脚本 |
| C-07 | `[x]` | 活动 Skill 持久化 | interaction payload 固定 `skill_id + version`；相同值幂等 |
| C-08 | `[x]` | 活动 Skill 禁止切换 | 后续 find/load/execute 只能继续固定 Skill |
| C-09 | `[x]` | `ask_user` 等待终态 | Root WebSocket 可等待；schedule/subagent 不暴露 |
| C-10 | `[x]` | steer 恢复固定 Skill | 恢复指令和 loaded 状态，不重新召回 |
| C-11 | `[x]` | 版本漂移失败闭合 | snapshot 缺少固定版本时 partial，不静默升级 |
| C-12 | `[x]` | History 与 Memory 输入 | History、pinned Memory 和最新 steer 进入同一主 Loop |
| C-13 | `[x]` | 按需 query-aware Memory | 只通过 tenant-scoped `memory` tool 召回，不做自动二阶段调用 |
| C-14 | `[x]` | 调用数基线 | 简单知识回答 1 次；工具请求仅增加标准 Tool continuation |
| C-15 | `[x]` | Provider 中立工具选择 | 通用 Loop 不发送 `required`；工具存在时沿用 OpenAI-compatible 默认自动选择 |
| C-16 | `[x]` | 无输出形态纠正轮 | `ask_user` / `final_response` 是结构化快速路径；普通文本直接成为兼容终态 |
| C-17 | `[x]` | 能力候选 advisory 边界 | `find` 候选只表示已通过服务端过滤，不自动升级为必须 load/execute 的业务合同 |

验收证据：统一 Loop、知识工具、活动 Skill、等待恢复、能力安全与 durable worker 回归测试通过。

## 7. Slice D：MCP Tool Policy 与自动并行

目标：知识型与功能型 Root Agent 都服从服务端 MCP Tool Policy；自动查询走快路径，需要确认的工具进入同一持久化审批。

| ID | 状态 | 待执行项 | 完成条件 |
| --- | --- | --- | --- |
| D-01 | `[x]` | 定义 `tool_policies` 服务端字段 | name/description/schema/hash/effect/approval；不信任 `readOnlyHint` |
| D-02 | `[x]` | 新增不可变 Alembic migration | `0054_mcp_tool_policies` 具备 upgrade/downgrade |
| D-03 | `[x]` | 更新管理 API/OpenAPI/前端契约 | 管理员基于发现结果显式分类；仅 read 可 automatic |
| D-04 | `[x]` | Runtime 校验 tenant/binding/schema hash | 任一不匹配均 fail closed |
| D-05 | `[x]` | 共享 Loop 接入 MCP | 只有模型按需调用时才发现，执行前重新校验策略 |
| D-06 | `[x]` | 非自动工具进入审批或拒绝 | Root WebSocket 进入审批；不支持入口拒绝 |
| D-07 | `[x]` | 安全回归测试 | Schema 漂移、绑定、写 Tool 和参数 Schema 均 fail closed |
| D-08 | `[x]` | MCP 跨 Server 有界并行发现 | 首轮 Prompt 前不远程发现；执行时发现并重新核对 hash |

验收证据：管理配置到 Runtime 执行形成完整链路，并有 tenant/RLS 和 Schema 漂移测试。

## 8. Slice E：一次性 Subagent 闭环

目标：入口和 Root Loop 都可分解，但不建设多波次工作流系统。

| ID | 状态 | 待执行项 | 完成条件 |
| --- | --- | --- | --- |
| E-01 | `[x]` | 一 Root 最多一块 TaskBoard | waiting/terminal Board 存在时均拒绝再次 dispatch |
| E-02 | `[x]` | 定义并应用 `DelegationGate` | 仅 Root、非 waiting/final、预算允许、任务只读独立 |
| E-03 | `[x]` | 删除无效 `agent_id` Tool 参数 | Child 继承 Parent 服务端运行配置 |
| E-04 | `[x]` | 正常 Root Loop 条件暴露 dispatch Tool | Child 和不合格阶段永远不可见 |
| E-05 | `[x]` | 中途 dispatch 保存有限 `resume_messages` | 标准消息、无 reasoning、默认 64 KiB，超限串行降级 |
| E-06 | `[x]` | TaskBoard 汇总进入 Renderer | 全终态 Board 直接进入最终汇总，不重跑 Planner |
| E-07 | `[x]` | Parent 保有审批/写操作/澄清 | Child 不支持审批、递归和 schedule |
| E-08 | `[x]` | TaskIQ 恢复测试 | worker 从持久化 Board/snapshot/action 恢复；完成 Board 不重复 dispatch |
| E-09 | `[x]` | 入口与 Loop 两类 E2E | 入口、Loop、预算、最后 Child 重投 Parent 均有测试 |

验收证据：同一 Root 无法创建第二块 Board；Parent 最终只输出一次；Child 过程无公开 delta。

## 9. 发布闭环

| ID | 状态 | 待执行项 | 完成条件 |
| --- | --- | --- | --- |
| R-01 | `[x]` | 测试 Agent 灰度开关 | direct rendering 与 Loop Subagent 可独立回退；旧知识并行开关仅保留配置兼容 |
| R-02 | `[x]` | 建立固定回归样例集 | Provider、direct、knowledge、Tool、审批、Subagent、恢复均有固定测试 |
| R-03 | `[-]` | 建立阶段耗时对比 | 已记录知识路径 Provider/公开/完成阶段；优化前和其余路径待补 |
| R-04 | `[x]` | 运行后端定向测试 | 后端全量 395 项、性能合同 6 项及前端定向测试均通过 |
| R-05 | `[-]` | 运行根质量检查 | 本次变更面检查通过；根检查被既有超长测试文件阻断，已单独记录 |
| R-06 | `[x]` | 更新运行手册和清单 | 配置、回滚、诊断字段和限制已写入运行手册 |
| R-07 | `[ ]` | 删除过渡路径 | 仅在旧 checkpoint 全部过期且灰度稳定后执行 |
| R-08 | `[x]` | 更新交互与安全标准 | Tool Policy、结构化 action 和不支持入口的失败边界成为正式合同 |

### 9.1 2026-07-19 验证记录

已通过：

```text
backend/.venv/bin/pytest -q                         377 passed
backend/.venv/bin/pytest -q tests/test_agent_runtime_performance_contract.py
                                                       6 passed
frontend npm run test -- --run <本次六个定向测试文件>  17 passed
frontend npm run build                               passed
frontend npm run api:check                           passed
frontend npm run lint                                passed
frontend npm run typecheck                           passed
backend Alembic heads                                0054_mcp_tool_policies (head)
```

本次新增或修改的后端 Python 文件已分别通过 Ruff format、Ruff check 和 Pyright；本次修改的前端文件已通过
Prettier、ESLint、TypeScript 和 Ant Design changed-file 检查。

根命令 `./scripts/check.sh` 当前在第一阶段被既有文件
`frontend/src/features/admin/KnowledgePage.test.tsx` 的 692 行阻断（上限 600），尚未运行完后续阶段。已单独核对的
既有基线债务还包括两个知识页面文件的 Prettier、`Pages.test.tsx`/`KnowledgePage.test.tsx` 的全量测试断言，
以及两个既有后端测试文件的全量 Pyright 报错；这些文件均不在本次实现修改面内。R-05 因而保持 `[-]`，
不得把“定向检查通过”描述成根质量检查全绿。

PERF-05、R-03 只能在测试环境用相同模型、配置和数据完成真实端点 p50/p95 对比；R-07 必须等旧 checkpoint
过期且灰度稳定后再删除过渡恢复路径，二者都不是当前代码阶段可伪造关闭的条目。

### 9.2 2026-07-20 本地迁移与真实端点基线

- 本地 Docker PostgreSQL 已从 `0053_remove_capability_state` 升级到 `0054_mcp_tool_policies`；列为
  `JSONB NOT NULL`、无长期数据库默认值，升级后不存在 NULL 行。没有在承载本地数据的数据库执行 downgrade。
- 新增 `scripts/benchmark_interaction_websocket.py`，真实请求必须显式确认，且不采集回答正文。
- 知识路径 10 个计入样本全部完成；修复后 accepted p50/p95 为 25.8/40.0 ms，首段为
  2.35/2.93 s，完成为 5.78/6.25 s。
- Provider 首内容到 durable 公开首段 p50/p95 为 15.6/20.1 ms，说明公开事件提交不是当前主要延迟。
- 实测发现 OpenAI-compatible 端点偶发严格 `json` Markdown fence；共用解析器在不放宽到任意文本提取的前提下
  支持单 fence，知识 Intent fallback 从 3/11 降为 0/11。
- 终态事件原先会提前清除 worker lease，导致后终态 `run_completed` 诊断被 fence 丢弃；现由 worker finally
  统一释放，真实端点已验证 `public_first_delta` 与 `run_completed` 均落库。
- 增补兼容性和 lease 回归后，后端全量为 `386 passed`，性能合同仍为 `6 passed`。
- 修复 `waiting_user_input -> steer` 恢复投递后，后端全量为 `387 passed`；前端补充信息等待态与
  WebSocket 传输定向测试为 `9 passed`。
- Knowledge Intent 改为非交互归纳、非交互入口关闭 `ask_user`，并升级多轮会话账本后，后端全量为
  `395 passed`；本地数据库已升级到 `0055_message_sequence`，历史 waiting/steer 事件已完成回填。

详细环境、两轮数字和不可推导的边界见
[Agent Runtime 性能基线](agent-runtime-performance-baseline.md)。PERF-05 和 R-03 仍为 `[-]`：当前没有功能型
测试 Agent 的优化前对照，也没有单 Tool/Subagent 的真实 staging 样本。

### 9.3 2026-07-20 知识型统一 Loop 验证

- 删除 `KnowledgeIntentAnalyzer`、默认 6 候选目录、`KnowledgeTurnCoordinator` 和
  `KnowledgeEvidenceCollector`；知识型请求直接进入共享 `AgentCompletionLoop`。
- instruction-only Skill 首次 load 后固定 `skill_id + version`；`ask_user -> interaction.steer` 恢复同一 Skill，
  禁止再次召回或切换，版本缺失时以 partial 失败闭合。
- 后端全量 `417 passed`；本次 Python 修改面 Ruff 与 Pyright 定向检查通过。
- 根 `./scripts/check.sh` 仍在既有 `frontend/src/features/admin/KnowledgePage.test.tsx` 692 行处被 600 行上限阻断；
  后端全量 Ruff 仍被既有 Alembic `0040_conversation_message_index_outbox.py` 两处超长行阻断。

### 9.4 2026-07-20 同会话原生历史验证

- 跨已结束 Interaction 的同会话近期历史不再扁平化成 XML user block；按原生 user/assistant role 和持久化时间
  直接进入共享 Loop，保留配置化 turn/token 预算，且不增加前置 LLM 调用。
- 等待中的 Interaction 继续使用 durable sequence 恢复当前 Interaction 的完整 transcript；功能型 Planner、活动 Skill
  检查点、Subagent 和完成门均未改变。
- 后端全量 `423 passed`；本次 Python 修改面 Ruff 与 Pyright 定向检查通过。
- 根 `./scripts/check.sh` 仍由既有 `frontend/src/features/admin/KnowledgePage.test.tsx` 692 行超过 600 行上限阻断。

### 9.5 2026-07-21 Durable 领取与 Provider 中立完成协议

- 本地 Durable Runtime 不再用 `recovery_lease_seconds=0` 表示可立即领取；accepted 阶段不写占位租约，避免 TaskIQ
  消息在数据库时间精度窗口内被确认后静默跳过。
- 通用 Loop 不再把非空召回候选升级为必执行合同，也不为强制 `ask_user` / `final_response` 输出形态追加纠正轮。
- 所有模型沿用 Provider 默认工具选择，不发送 `tool_choice=required`；结构化终止工具仍可用，普通文本直接交付。
- OpenAI-compatible 流式错误先读取 body 再执行错误分类，避免 `ResponseNotRead` 把 Provider 400 覆盖成内部异常。
- 后端全量回归与本次修改面 Ruff、Pyright 通过。根检查仍被既有
  `backend/tests/test_operations_services.py` 608 行和
  `frontend/src/features/admin/KnowledgePage.test.tsx` 692 行超过 600 行上限阻断。

## 10. 暂不进入 Checklist

- 第二波 Subagent、递归 Child、Delegation Ledger。
- 通用 Evidence Scheduler/Graph/Merger。
- 新 OutputCheckpoint、事件批量 API、先发送后保存。
- 完整 ContextEnvelope、自动 History 摘要，以及知识入口之外的自动 query-aware Memory 召回。
- Provider 自动探测、Capability Profile 平台和模型名特判。
- 并行写操作或 Child 执行审批/不可逆动作。

出现真实、可复现的需求或监控证据后，再为这些能力单独立项。
