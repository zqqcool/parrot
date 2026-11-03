# 知识型 Agent 图文回答与引用锚点方案

> 状态：R0–R2 最小闭环已落地（observation catalog、出站 citations/media、interaction-scoped media、Chat 来源卡）；R3 语义召回与 R4 截断治理仍待完善  
> 日期：2026-07-24  
> 依据：当前 `SqlKnowledgeRuntime` / `knowledge_search` / IM `ai.output.*` / `ChatPage`、  
> `docs/knowledge-multimodal-implementation-plan.md`、ADR 0003、以及近期 run  
> `interaction_FQUFY95…` / `interaction_Ugj0cGF…` 的实测问题。  
> 产品约定变更：**Agent 对话从「仅文本」改为「图文 + 可验证引用」**；多库并行绑定视为正常场景（含噪声库）。

---

## 1. 问题陈述（以代码事实为准）

### 1.1 现状链路

```text
knowledge_search
  → SqlKnowledgeRuntime.retrieve
      → 多空间并行 rank（各空间自有 embedding / top_k / rerank）
      → 跨空间 RRF → tool.limit（默认 6，上限 12）
      → expand_evidence_bundle（内部已有 media_refs）
  → execution_helpers._knowledge_result
      → 仅序列化 evidence(文本) + citation_ids   ← media_refs 丢弃
  → model_observation 再截断（单字段 ~2k / 整包 ~12k）
  → 模型自由文本作答
  → ai.output.* 仅 content 字符串
  → ChatPage MarkdownPreview 纯文本渲染
```

管理端召回测试已能通过 `media_refs` + `/knowledge/media/{id}/content` 预览；**IM / Agent 出站未接这条链**。

### 1.2 已确认缺陷（与多库噪声无关的部分）

| 问题 | 证据 | 影响 |
|------|------|------|
| 语义漏检 / 问句分解不足 | 「创建/同步」命中创建页 + 天眼查，漏掉 ERP「同步客户」slide-10 | 答案结构看似完整，事实边界错 |
| 答案无 citation 锚点 | Prompt 只要求「有 citation 时准确引用」，无机器可解析格式、无服务端校验 | 前端无法挂图/展开；审计无法核对 |
| 图不达对话 | tool 不回 `media_refs`；公开事件无附件；访客无 media URL | 即使用户要截图，链路也断 |
| observation 截断 | `…[truncated_for_model]` 裁掉后半证据 | 模型只看前几条，加重漏用 |

多库并行 + RRF 截断是既定能力。跨库默认仍为各空间内 rank → RRF → `tool.limit`。
租户可在知识库列表配置 **多库合并重排**：当 `spaces_with_hits >= 2` 且开启并绑定 reranker 时，每库最多取 12 条候选，对 RRF 候选再 rerank；成功、阈值过滤、失败回退和证据扩展后的最终条数均不超过 `min(tool.limit, result_top_k)`。详见实现与 `knowledge_merge_settings`。

---

## 2. 产品目标（新约定）

1. **图文回答**：知识型 Agent 在 IM / WebSocket 对话中可展示与引用对应的截图（slide_render / 主缩略图），而不仅是文字步骤。  
2. **可验证引用**：每条关键企业事实必须带机器可解析的 `citation_id`；UI 可展开原文与图组。  
3. **图默认不进 LLM**：继续遵守「原件/图像字节不进 tool observation / 向量库」；图由**服务端结构化附件**挂到回答上，模型只决策「用哪些 citation」。  
4. **多库并存**：Agent 绑定多空间是正常；跨库默认 RRF；可选租户级合并 rerank（≥2 库命中时）。

非目标（本阶段仍不做）：

- 把多张大图灌进模型视觉上下文 / ColPali  
- 访客匿名枚举任意 knowledge media  
- 飞书/钉钉等非 WebSocket 渠道的富媒体适配（可预留同一结构化附件契约）  
- **无配置时强制全局 rerank**（须租户开启多库合并配置才触发）
- Agent 级覆盖合并策略、可配置命中阈值（当前写死 ≥2）

---

## 3. 目标架构

```mermaid
sequenceDiagram
  participant U as IM Chat
  participant R as Agent Runtime
  participant K as KnowledgeRuntime
  participant M as Model
  participant O as Output assembler

  U->>R: interaction.create
  R->>M: loop + knowledge_search
  M->>R: knowledge_search(query[, subqueries])
  R->>K: retrieve (+ optional multi-query)
  K-->>R: EvidenceBundle(items + media_refs)
  R->>M: bounded text evidence + citation catalog<br/>(ids/anchors/titles only; no image bytes)
  M-->>R: answer text with cite markers OR structured cites
  R->>O: validate cites ⊆ retrieved set<br/>attach primary media per cite
  O-->>U: ai.output.completed<br/>{content, citations[], media[]}
  U->>K: authorized media content by asset_id
```

原则：**检索扩证据 → 模型只引用 ID → 服务端装配图文 → 客户端渲染**。不信任模型手写图片 URL。

---

## 4. 契约变更

### 4.1 `knowledge_search` observation（对模型）

在现有字段上增加**轻量目录**，仍禁止塞图字节：

```json
{
  "status": "ok",
  "retrieval_status": "ok",
  "evidence": "<knowledge-evidence>…文本 excerpt…</knowledge-evidence>",
  "citations": [
    {
      "citation_id": "knowledge_chunk_…",
      "title": "CRM三期-整合版",
      "anchor": "slide-4",
      "slide_no": 4,
      "space_id": "knowledge_space_…",
      "has_media": true,
      "primary_media_kind": "slide_render"
    }
  ],
  "citation_ids": ["…"],
  "space_count": 2,
  "retrieval_method": "hybrid_rerank"
}
```

- `evidence` 继续 bounded；优先保证 **每条 citation 的标题行 + 前 N 字不被整包截断策略误伤**（见 §6.3）。  
- `media_refs` **完整列表不进模型**；只暴露 `has_media` / kind，避免上下文膨胀。

实现落点：`execution_helpers._knowledge_result` + `KnowledgeEvidenceBundle` 序列化；`runtime_helpers.render_evidence` 可保留。

### 4.2 公开出站：`ai.output.completed`（及可选 delta 元数据）

在 `content` 之外增加结构化字段（访客可见，需符合 `event_visibility` 白名单）：

```json
{
  "output_id": "output_…",
  "content": "……（可含可读引用标记）……",
  "runtime_status": "completed",
  "citations": [
    {
      "citation_id": "knowledge_chunk_…",
      "title": "CRM三期-整合版",
      "anchor": "slide-4",
      "slide_no": 4
    }
  ],
  "media": [
    {
      "citation_id": "knowledge_chunk_…",
      "asset_id": "knowledge_media_asset_…",
      "kind": "slide_render",
      "role": "primary",
      "alt": "幻灯片 4"
    }
  ]
}
```

- `delta` 阶段可只流式 `content`；`completed` 一次性带齐 `citations` / `media`。  
- 更新：`output.py` / `terminal_delivery.py`、AsyncAPI、`interaction-contract.md`。

### 4.3 访客可授权的 media 读取

现有 `GET .../admin/.../knowledge/media/{asset_id}/content` 依赖管理权限，IM 访客不可用。

新增其一（推荐 A）：

| 方案 | 说明 |
|------|------|
| **A. Interaction-scoped media** | `GET /api/v1/im/...` 或与 visitor session 绑定：仅当 `asset_id` 属于**本 interaction 已投放的 output.media** 时可下载；TTL = interaction/会话窗口 |
| B. Short-lived signed URL | 出站时签发短时 object URL；实现简单但密钥与 CDN 边界更重 |

A 与现有「citation 固定 version + 再授权」一致，优先。

### 4.4 回答内 citation 锚点（对模型 + 服务端）

采用**双轨**：

1. **模型输出可读标记**（写入 `content`，便于 Markdown）：  
   `[^cite:knowledge_chunk_xxx]` 或 `【cite:knowledge_chunk_xxx】`（二选一，全局统一）。  
2. **服务端校验与补全**：  
   - 从本轮（及允许的近轮）`knowledge_search` 结果收集 `allowed_citation_ids`；  
   - 抽取正文中的 cite 标记；非法 ID 剥离或降级为纯文本；  
   - 若正文有企业事实句但 **零合法 cite**：触发一次轻量纠偏（提示模型补 cite）或标记 `citations_incomplete`（产品可选强硬/宽松）。  
3. **装配 `output.citations`**：取「正文引用 ∪ 模型结构化 cites」∩ allowed；每条选 1 张 primary media（优先 `slide_render`，否则组内 ordinal 最小 embedded）。

Prompt（`_KNOWLEDGE_POLICY`）改为明确格式与「不得无 cite 陈述内部操作步骤」。

---

## 5. 语义漏检改进（结合当前检索实现）

当前单次 `query` + 跨库 RRF 对复合问句（「创建/同步」）不稳定。推荐**分层**，均在现有 `SqlKnowledgeRuntime` 上扩展，不先上向量多模态。

### 5.1 P0 — 查询分解与租户级合并重排

跨库默认：各空间 `_rank_space` → `reciprocal_rank_fusion_many` → `tool.limit`。  
租户开启 `knowledge_merge_settings.merge_rerank_enabled` 且 `spaces_with_hits >= 2` 时：每库先截断至 12 条候选 → RRF 候选（上限 `rerank_top_n`）→ 合并 rerank → `min(tool.limit, result_top_k)`。外部重排不可用时按同一最终上限回退 RRF，后续 evidence expansion 也不得突破该上限。

| 手段 | 做法 | 落点 |
|------|------|------|
| 复合问句分解 | 模型或规则把「A/B」「以及」拆成 2–3 个 subquery，各跑 retrieve，再按 citation_id 去重后按现有合并语义收束 | `knowledge_search` 增可选 `queries: string[]`，或 runtime 轻量 split |
| 租户合并重排 | ≥2 库命中 + 配置开启 → 全局 rerank；`result_top_k` 控制交给 LLM 的条数 | `knowledge_merge_settings` + `SqlKnowledgeRuntime._configured_candidates` |

「创建」与「同步」分成两路时，slide-10 与 slide-4/5 同进候选池的概率显著上升。

### 5.2 P1 — 证据扩展与章节感知

已有 `expand_evidence_bundle`（章内 ±1）。补强：

- 命中目录页（如 slide-3 仅含「创建/同步客户」标题）时，**强制扩展同 chapter 后续步骤页**（已部分具备；需对 TOC-like 短页加权）。  
- 同 title 前缀（`客户 – 客户同步`）优先并入 expand，而不仅依赖向量邻居。

### 5.3 P1 — 漏检感知再检索

沿用 `knowledge_retry`（no_results 可再搜一次）扩展语义：

- 用户问句含多个动词/斜杠结构，且返回 citations 的 anchor/title **覆盖率不足**（启发式：子意图关键词未出现在任一 excerpt）→ 允许 **一次** refined `knowledge_search`，不受「近义重复」误杀。  
- 与 `knowledge_repetition` 白名单协同：仅当 `reason=coverage_gap` 时放行。

### 5.4 P2 — 评测

在 `knowledge/evaluation.py` 增加金样：

- 问句：`CRM创建/同步客户的步骤`  
- 必须命中：slide-4/5（创建）+ slide-10（ERP 同步）；slide-8 天眼查不得替代 slide-10。  
- Agent 端到端：output 含对应 `citation_id` + 至少 1 个 primary media。

---

## 6. 上下文与截断治理

多库命中后「量太大」的现有阀门保留，并收紧**保真优先级**：

| 层 | 现状 | 调整 |
|----|------|------|
| 候选 | 每空间 `candidate_top_k` | 合并重排时服务端固定 `per_space_candidate_cap = 12`；前端从策略响应读取，不重复硬编码 |
| 合并 | 跨空间 RRF → tool `limit`；若租户合并重排启用且命中库 ≥2，再 rerank 并截断为 `min(tool.limit, result_top_k)` | 复合查询多路召回后仍用同一合并规则 |
| excerpt | `bounded(..., 800)` | 保持 |
| tool → 模型 | 整包 12k / 字段 2k | **citations 目录优先于 evidence 长文**；evidence 按 rank 截断，禁止只保留前 2k 字符导致后半 citation 消失 |
| 图 | 不进模型 | 继续；只进 `output.media` |

伪代码：

```text
observation = {
  citations: compact_catalog(items),          # 先放
  evidence: render_evidence(items, max_chars=BUDGET - len(catalog)),
  ...
}
```

---

## 7. 前端（IM Chat）

`ChatPage` 在 `ai.output.completed` 时：

1. 继续用 `MarkdownPreview` 渲染 `content`。  
2. 解析 cite 标记高亮；点击 → 调用**访客 citation/media API**（非 admin）。  
3. 渲染 `media[]`：复用 `KnowledgeEvidenceMediaStrip` 思路（blob + PreviewGroup），数据源改为 output 附件 + visitor 鉴权下载。  
4. 无 `media` 时不占位；有 cite 无图时显示文本引用卡即可。

管理端召回 UI 保持现状，作为「完整图组展开」参考实现。

---

## 8. 安全与租户

- 所有 media/citation 读取必须：`tenant_id` +（interaction 投放集合 ∨ 管理权限）。  
- 租户不可见资源继续 404。  
- 公开事件不得带 object storage key、签名密钥、内部 score。  
- Visitor cookie 会话与现有 IM 一致；media 下载走同一凭据，禁止 `localStorage` token。

---

## 9. 里程碑

| 阶段 | 范围 | 验收 |
|------|------|------|
| **R0 契约** | output / AsyncAPI / observation catalog；ADR 0003 与 multimodal §12 改「图文」 | 契约测试绿；旧客户端忽略新字段仍可看文本 |
| **R1 引用锚点** | Prompt 格式 + 服务端 cite 校验/剥离 + `output.citations` | run 复现「创建步骤」时 completed 带合法 citation_ids |
| **R2 对话出图** | interaction-scoped media API + Chat 附件条 | IM 页对 slide-4/5 显示至少 1 张主图 |
| **R3 语义召回** | 租户合并重排（≥2 命中）已落地；多 query / coverage_gap 再搜待实现 | 合并配置、失败回退与 TopK 约束测试已绿；完整 R3 仍须金样命中 slide-10，且天眼查不替代 ERP 同步 |
| **R4 截断治理** | observation 保真截断 | 6 条 citation 目录在截断后仍完整可见于模型输入诊断 |

建议顺序：**R0 → R1 → R2**（产品可见图文）与 **R3** 可并行（质量）。跨库排序默认 RRF；合并 rerank 由租户配置门控。

---

## 10. 与既有文档的关系

| 文档 | 变更 |
|------|------|
| 本文件 | 图文回答 + 引用 + 漏检主方案 |
| `knowledge-multimodal-implementation-plan.md` §12 | `Agent V1 只吃文本` → `Agent 对话图文（结构化附件；图不进 LLM）` |
| ADR 0003 | Consequences：observation 仍无图字节；**出站允许结构化 media 引用** |
| `knowledge-action-agent-architecture.md` §4.3 / §5 | 补充「回答必须可解析 citation；IM 可挂 primary media」 |
| `interaction-contract.md` | `ai.output.completed.data` 增 `citations` / `media` |

---

## 11. 决策待评审

1. Cite 标记语法：`[^cite:id]` vs `【cite:id】`？  
2. 无 cite 的步骤类回答：硬失败重试一次，还是交付并打 `citations_incomplete`？  
3. Media 访客 API：interaction-scoped（推荐）还是 signed URL？  
4. 复合查询：模型传 `queries[]`，还是 runtime 规则拆分「/、以及、和」？

其余未实现决策评审锁定后按 §9 推进；租户级多库合并重排以当前代码、迁移和测试为准。
