# 多能力编排实施 Checklist

> 状态：实施中
> 唯一设计依据：[Parrot Skill、MCP 与 Subagent 最终编排方案](multi-capability-orchestration-design.md)
> 日期：2026-07-21

## 1. 使用规则

- `[x]`：代码、测试和必要文档均已完成并核对。
- `[-]`：已有基础，但尚未满足完成条件。
- `[ ]`：尚未实施。
- `[!]`：正确性、安全或上线阻断项；必须优先关闭。
- 每个 Slice 独立提交和灰度；不得跨 Slice 顺手加入递归 Child、多 TaskBoard 或通用工作流 DSL。
- 功能型 Planner 不重构；知识型请求不增加前置 LLM。
- 配置写入选定 `dev.toml`、`sit.toml`、`prod.toml` 的 typed config，不读取环境变量。

## 2. 当前基线与已确认缺口

| ID | 状态 | 事实 | 证据 |
| --- | --- | --- | --- |
| BASE-01 | `[x]` | 功能型 Planner 与统一 Agent Loop 已存在 | `turn_planning.py`、`in_process.py` |
| BASE-02 | `[x]` | 知识型请求无前置 Intent LLM | `knowledge_execution.py` |
| BASE-03 | `[x]` | Child Interaction、TaskBoard、TaskIQ 恢复链已存在 | `subagent_dispatcher.py`、`taskboard.py`、`durable.py` |
| BASE-04 | `[x]` | MCP policy 已验证 effect、approval、schema hash | `mcp_servers/tool_policy.py`、`capabilities.py` |
| GAP-01 | `[x]` | Primary Skill 曾阻断不同 capability ID，包括 MCP ID | Slice B 已修复 |
| GAP-02 | `[x]` | Knowledge Root 已按 Root/开关/Board 闸门暴露 `subagent_dispatch` | `plan_tools.py`、`delegation_gate.py` |
| GAP-03 | `[x]` | Loop Tool 支持单个结果依赖 Child | `builtin_tools.py`、`taskboard.py` |
| GAP-04 | `[x]` | 串行 Child 只接收声明依赖的受限结果 | `subagent_task_prompt.py` |
| GAP-05 | `[x]` | Loop Child 完成后以标准 Tool Result 恢复原 Loop | `subagent_continuation.py`、`in_process.py` |
| GAP-06 | `[x]` | Child profile 从 Parent 派生只读能力子集 | `subagent_scope.py` |
| GAP-07 | `[x]` | Observation 已区分 instruction/read/action/subagent/failure；指令不再伪装为动作回执 | `observations.py` |
| GAP-08 | `[x]` | 并行覆盖纯内置、知识检索与显式安全的自动只读 MCP，并保留串行屏障 | `tool_batches.py`、`tool_policy.py` |
| GAP-09 | `[-]` | Task 数量和 Child 并发已配置化；总 timeout/tool budget 仍保留硬安全上限 | `config.py`、`taskboard.py` |

## 3. Slice A：固定根因回归测试

| ID | 状态 | 待执行项 | 完成条件 |
| --- | --- | --- | --- |
| A-01 | `[x]` | Primary Skill 后执行已绑定自动只读 MCP | 回归测试证明不再产生 Skill conflict |
| A-02 | `[x]` | Primary + Supporting Skill | 加载、执行、限额和 checkpoint 均有测试 |
| A-03 | `[x]` | 单任务 Subagent | Tool Schema 与 TaskBoard 均覆盖一项 task |
| A-04 | `[x]` | 知识型 Root Loop Tool 可见性 | Root/Child、开关和 Board 闸门有回归测试 |
| A-05 | `[x]` | Task B 接收 Task A 结果 | 只注入声明依赖且带 reference-data 边界 |
| A-06 | `[x]` | Loop-origin Board 恢复 | Tool Call + Tool Result 后仍可继续调用其他 Tool |
| A-07 | `[x]` | required Child 失败 | Parent 可解释失败但终态固定为 partial |
| A-08 | `[x]` | instruction-only 完成证据 | 测试固定 `instruction_ready` 为 instruction，而非 action receipt |
| A-09 | `[ ]` | tenant 与 binding 回归 | 跨 tenant、未绑定 capability 保持 fail closed |
| A-10 | `[ ]` | Provider 兼容合同 | 普通文本、Tool Call、thinking 私有字段和流式参数累积均覆盖 |

## 4. Slice B：SkillContext 与能力合同

| ID | 状态 | 待执行项 | 完成条件 |
| --- | --- | --- | --- |
| B-01 | `[x]` | 定义 `SkillContextV1` | `primary + supporting + schema_version` 有 typed parser/serializer |
| B-02 | `[x]` | 兼容旧 checkpoint | 旧 `active_skill` 映射为 Primary；只写新格式 |
| B-03 | `[x]` | 原子持久化 | tenant row lock 下固定版本；重复相同值幂等 |
| B-04 | `[x]` | Supporting 数量配置化 | 上限来自三套 typed TOML，默认 3 |
| B-05 | `[x]` | 修正 MCP 冲突 | 能力类型识别先于 Skill identity 检查 |
| B-06 | `[x]` | Supporting 加载 | 同一 Interaction 可加载有限、固定版本 Supporting Skill |
| B-07 | `[x]` | 版本漂移 fail closed | Primary/Supporting 任一版本缺失均 partial |
| B-08 | `[x]` | `capability_id` 新字段 | Tool Schema 只发布新字段；Runtime 兼容旧 `skill_id` |
| B-09 | `[x]` | load role | `capability_search(load)` 支持并校验 `primary|supporting` |
| B-10 | `[x]` | Prompt 优先级 | 平台/Agent > Primary > Supporting；Skill 以 Tool Result 注入 |
| B-11 | `[x]` | 恢复 Prompt | steer/worker 恢复时重建全部固定 Skill 指令 |
| B-12 | `[x]` | 诊断 | 只记录 Skill ID、version、role 和状态 |

## 5. Slice C：单层结果型 Subagent

| ID | 状态 | 待执行项 | 完成条件 |
| --- | --- | --- | --- |
| C-01 | `[x]` | Task 数量改为 1..N | Loop Tool 为 1..N；功能型 Planner 保持既有 2..5；N 配置化且不超过 5 |
| C-02 | `[x]` | `required` 字段 | 旧任务缺省 true；持久化和恢复稳定 |
| C-03 | `[x]` | `capability_scope` | Primary、Supporting、MCP IDs 均校验 Parent binding |
| C-04 | `[x]` | 派生 Child profile | Child 只能收窄权限；scope 外能力不可发现和执行 |
| C-05 | `[x]` | Child Primary Skill | Child payload 固定 scope 中 Primary/Supporting 版本 |
| C-06 | `[x]` | Child Tool 边界 | 无 ask_user、approval、schedule、subagent、script 和非自动写 Tool |
| C-07 | `[x]` | 依赖结果注入 | `render_task_contract(task, dependency_results)` 有长度和信任边界 |
| C-08 | `[x]` | 结果 Schema | 受限 JSON Schema 禁止远程引用；不合法结果按 task failed 结算 |
| C-09 | `[x]` | `SubagentResultV1` | Parent 只接收 status/content/structured_output/error_code |
| C-10 | `[x]` | Loop resume snapshot | 持久化 `resume_messages`、`resume_plan`、`dispatch_call_id` |
| C-11 | `[x]` | 标准 Tool continuation | Board 完成后追加 Tool Call + Tool Result 并恢复原 Loop |
| C-12 | `[x]` | Planner-origin 兼容 | 功能型入口 Board 仍一次汇总，不重跑 Planner |
| C-13 | `[x]` | required 失败状态 | required task 非 succeeded 时 terminal status 为 partial |
| C-14 | `[x]` | 幂等 settlement | row lock、terminal guard 和重复 dispatch 不再重复 enqueue Child |
| C-15 | `[x]` | 一 Root 一 Board | waiting Board 幂等复用；terminal Board 拒绝第二块 Board |
| C-16 | `[x]` | Knowledge Root 暴露 dispatch | 开关、预算、Root 状态满足时可见 |
| C-17 | `[x]` | Functional Loop 暴露 dispatch | agent_loop/capability_lookup 均可见；Planner 合同保持不变 |
| C-18 | `[x]` | Child 无公开输出 | Actor 公开读取仅允许 runtime_depth=0；Child 仅保留内部事件 |

## 6. Slice D：完成证据

| ID | 状态 | 待执行项 | 完成条件 |
| --- | --- | --- | --- |
| D-01 | `[x]` | Observation 枚举 | instruction/read/action/subagent/failure/control 类型稳定 |
| D-02 | `[x]` | 删除布尔捷径 | `instruction_ready` 为 instruction，不是 action receipt |
| D-03 | `[x]` | waiting Board 完成门 | dispatch 后 Root 进入持久化 waiting，不处理普通终态候选 |
| D-04 | `[x]` | required Child 完成门 | required task 非 completed 时 Parent 终态固定 partial |
| D-05 | `[x]` | Planner capability 门 | Planner 不变；find/load 中间态不再绕过完成门 |
| D-06 | `[x]` | Tool 失败可说明 | 已取得相关 capability failure 后可如实交付限制说明 |
| D-07 | `[x]` | LLM 异常用户状态 | Worker 将 Provider/协议失败映射为公开 failed 事件 |
| D-08 | `[x]` | 审批边界 | pending approval 只能 Root 恢复，Child 受控失败 |

## 7. Slice E：安全并行与配置

| ID | 状态 | 待执行项 | 完成条件 |
| --- | --- | --- | --- |
| E-01 | `[x]` | Tool batch 分段 | parallel-safe 连续段与串行屏障保持调用顺序 |
| E-02 | `[x]` | MCP `parallel_safe` | server-owned policy 字段，缺省 false |
| E-03 | `[x]` | Policy 校验 | 仅 read + automatic + parallel_safe 可并行 |
| E-04 | `[x]` | Child capability 冲突 | 共享非并行或未知 MCP 时 TaskBoard 串行化 |
| E-05 | `[x]` | 独立 Child 并发 | 无依赖且 scope 安全时最多配置上限并行 |
| E-06 | `[-]` | 配置迁移 | task/parallel/supporting 已 typed；Child 总 budget 仍为硬安全上限 |
| E-07 | `[x]` | 三套 TOML | dev/sit/prod 使用同一显式合同 |
| E-08 | `[x]` | 管理契约 | MCP policy OpenAPI/管理端支持显式安全字段 |
| E-09 | `[x]` | 稳定顺序 | gather 与 TaskBoard 均按定义顺序写回，不按完成先后排序 |
| E-10 | `[-]` | 压力与限流 | 已有配置上限和排队语义；尚缺墙钟压力基线 |

## 8. Slice F：可观测性与灰度

| ID | 状态 | 待执行项 | 完成条件 |
| --- | --- | --- | --- |
| F-01 | `[ ]` | Route 诊断 | context/direct_tool/subagent 路由原因可查 |
| F-02 | `[ ]` | Child 阶段耗时 | queue/provider/tool/settle/root_resume 均记录 |
| F-03 | `[x]` | 完成证据摘要 | management trace 记录 decision/reason 和各 Observation 类型计数 |
| F-04 | `[x]` | Partial reason | capability_observation_required、required_subagent_failed 等稳定 |
| F-05 | `[ ]` | 灰度开关 | SkillContext、Loop Subagent、安全并行独立关闭 |
| F-06 | `[ ]` | 四路径基线 | direct、单 Tool、单 Child、三 Child 的 p50/p95 |
| F-07 | `[ ]` | 质量指标 | Tool 成功率、Child 失败率、partial/重复 dispatch 率 |
| F-08 | `[ ]` | 回滚验证 | 关闭新能力后旧单 Skill 路径仍可恢复 |

## 9. 必须通过的测试矩阵

### 9.1 功能

- [x] 普通知识回答仍为一次 LLM，不触发 capability discovery。
- [x] Primary + Supporting Skill 同一 Loop 可恢复。
- [x] Primary Skill 后 MCP 成功执行，不再冲突。
- [x] 一项结果依赖创建一个 Child，并回到 Parent Loop。
- [x] 两项独立任务按稳定顺序进入并发窗口；依赖任务严格串行并收到上游结果。
- [x] Parent 结果返回后仍可执行下一项 Tool；Skill/MCP 走同一 Completion Loop。
- [x] Parent 最终只输出一次；Actor 公开入口不能订阅 Child。

### 9.2 安全

- [ ] 跨 tenant、未绑定、未发布和版本漂移全部 fail closed。
- [x] Child capability scope 不能扩张 Parent profile。
- [x] Child 无法发起审批、写操作、schedule、ask_user、script 或递归委派。
- [ ] MCP Schema Hash 漂移、参数不匹配和 policy 禁止均失败闭合。
- [ ] 外部结果中的指令不能越过 reference-data 信任边界。

### 9.3 恢复与竞态

- [ ] dispatch 持久化后 Worker 中断，不重复创建 Child。
- [ ] 最后一个 Child 完成与 Parent redispatch 竞争时只恢复一次。
- [x] Parent Resume Snapshot 损坏时安全 partial。
- [x] 旧 `active_skill` checkpoint 可迁移，版本缺失不升级。

## 10. 当前验证记录

Slice B 至 Slice E 最终验证：

```text
backend pytest: 494 passed
frontend targeted MCP policy tests: 4 passed
frontend api:check / lint / typecheck / build: passed
targeted pyright: 0 errors
git diff --check: passed
```

前端全量测试当前为 `197 passed / 3 failed`。失败均位于本次未修改的既存用例：

```text
frontend/src/app/Pages.test.tsx
  opens a Run detail drawer from a user's conversation without changing the route
frontend/src/features/auth/ChangePasswordPage.test.tsx
  shows a request error without leaving the page
frontend/src/features/admin/KnowledgePage.test.tsx
  explains why a non-empty knowledge space cannot be deleted
```

Root 全量质量检查仍有两个既存文件大小基线：

```text
backend/tests/test_operations_services.py: 608
frontend/src/features/admin/KnowledgePage.test.tsx: 692
```
