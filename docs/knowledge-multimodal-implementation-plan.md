# 知识库多媒体落地方案（PPTX / DOCX / XLSX）

> 状态：M1–M4 + M2b DOCX + M2c XLSX 已落地；全保真 `slide_render` 依赖本机 soffice，缺失或失败时仅生成 `thumb` 降级预览并计入 `skipped_media_count`  
> 依据：当前 `backend/app/modules/knowledge/*`、`docs/knowledge-action-agent-architecture.md` §4.3、  
> Mytrina Operation Manual PPTX 样例、以及 2025–2026 多模态 RAG / Parent–Child / 结构感知切分实践。  
> 前提：入库文件经后期上传前审计后视为可信、可展示；Embedding（含日后多模态）由租户自配；本阶段不做恶意文件专项。

---

## 1. 今日代码事实（Gap）

| 能力 | 现状 |
|------|------|
| 上传类型 | 仅 `pdf` / `docx` / `md` / `txt`（`ingestion_validation.py`）；**无 pptx / xlsx** |
| 提取 | `extractor.py` 只抽纯文本；DOCX **仅 `paragraphs`**（丢表、内嵌图、页眉页脚）；无 OCR；无 PPTX/XLSX |
| 摄取 | `ingestion_worker.py`：读对象 → 抽文本 → 预处理 → `split_content` → chunks → 可选向量 job |
| Chunk | `content` + `citation_anchor=chunk-{n}` + `tsvector`；无 slide/sheet/section/group/media |
| 向量 | Milvus 仅存 `id/vector/tenant_id/space_id/document_version_id/chunk_id` |
| 证据 | `KnowledgeEvidenceItem` 仅文本 excerpt；无 `media_refs` |
| 依赖 | 无 `python-pptx` / `openpyxl`；已有 `pypdf` / `python-docx` / `pillow` |
| 架构预留 | §4.3 要求先做 `KnowledgeContentExtractorPort`，图不进 tool observation |

---

## 2. 实际需求（已对齐）

1. 同时覆盖 **PPTX、DOCX（Word）、XLSX** 三类业务文档（外加现有 pdf/md/txt 不回归）。  
2. 表格 / 幻灯片 / Word 中的图（多为操作路径）召回时能 **返回相关图片**。  
3. 关联图要 **成组返回**（上下页、同一步骤、同表区域），不能只回一张。  
4. 召回尽量准：按钮名、步骤文案、表头/单元格关键词可搜到。  
5. 原件与预览图放对象存储；**向量库不存图像二进制**。  
6. 向量模型用户自配；多模态向量后续再挂。  
7. 安全/恶意文件后置专项。

---

## 3. 统一契约 + 三分格式策略

三种 Office 格式共用同一套存储与召回契约，**仅 Extractor / 切分策略不同**。

```text
任意支持格式
  → staging / canonical
  → KnowledgeContentExtractorPort（按 MIME 路由）
  → （需要时）PageOrSheetRenderer / 内嵌图落盘
  → blocks → chunks + media_assets + evidence_groups
  → FTS ± 用户配置向量（文本）
  → 命中 → expand group → EvidenceBundle.media_refs
  → 授权预览；Agent 默认只吃文本
```

| format_profile | 语义单元（Parent） | 索引文本来源 | 主视觉 media | 成组键 |
|----------------|-------------------|--------------|--------------|--------|
| `pptx` | 1 slide | 标题 + 步骤副标题 + 正文/表 + notes | **slide_render（必做）**；embedded 次要 | `chapter_title` + `slide_no`；默认 ±1 |
| `docx` | 1 section（heading 子树）或连续「步骤」块 | 段落 + 表 Markdown + 图 caption/OCR | **embedded 图**（按文档序）；可选 section 首页预览 | `heading_path` / `procedure_step`；图与邻近正文强制同组 |
| `xlsx` | 1 sheet 内 1 个 `table_region`（或整 sheet 若小） | 表头 + 单元格值序列化 | **锚定到单元格的浮动图**；chart 渲染为派生图或标记 skipped | `sheet_name` + region；区内全部图同组 |
| `pdf` / `md` / `txt` | 维持现逻辑；后续可挂 page_render | 现有文本提取 | 可选后续增强 | 兼容旧 `chunk-N` |

---

## 4. 分格式设计细节

### 4.1 PPTX（样例：Mytrina Operation）

实测：~64 页；S3 架构图 **0 pic / 大量 shape**；操作章同标题最长 ~20 页；有 `1-2 Login` 类步骤副标题。

- 主视觉 = **每页 slide_render**（否则架构图无法返回）。  
- 1 slide = 1 证据页；禁用整 deck 字符乱切。  
- 成组：章内 ±1；短章 ≤3 整段；`diagram` 页附带同标题下一页 `table`。  
- 依赖：`python-pptx` + SlideRenderer（LibreOffice headless 等）。

### 4.2 DOCX（Word）— 相对现状「升级」而非新建格式

现状已允许上传，但提取残缺；本方案把 DOCX 升到与 PPTX 同级的结构化多媒体。

**提取（DocxExtractor）：**

1. 按 body 文档序遍历：段落、表格、drawing（内嵌图）。  
2. Heading 样式 → `section_path`（如 `3. 登录 > 3.1 SSO`）。  
3. 表格 → Markdown/TSV 写入 `index_text`；表内或紧邻图片挂同一 `evidence_group`。  
4. 内嵌图 → 抽出二进制 → `media_assets(kind=embedded)`，`ordinal` 为文档序；可选 OCR/受限 caption 并入同组可检索文本。  
5. 识别「步骤 N」/编号列表 → `procedure_step` 组，同一步多图共享 `group_id`。

**成组扩展：**

- 默认：同 `procedure_step` 或同 section 内邻接图 ±1。  
- 命中纯文本块时，带回该 section 内全部 `media_refs`（受 `max_media` 预算）。  

**渲染：**

- 不强制整文档 render；以 **embedded 原图** 为主预览。  
- 可选：复杂页（含 SmartArt）标记 `skipped_media` 计入摄取报告，避免静默丢失。

**依赖：** 强化现有 `python-docx`（读 rels/blip 取图）；必要时 Pillow 规范化。

### 4.3 XLSX（Excel）— 新增格式

**提取（XlsxExtractor，`openpyxl` read_only/data_only 按需）：**

1. 按 sheet 处理；跳过明显空表。  
2. 大表按「连续非空矩形」或命名区域切成 `table_region`，避免整表一个巨 chunk。  
3. `index_text` = sheet 名 + 表头 + 行文本（有上限；超限按区域再切，共享 `sheet_name`）。  
4. 浮动图：读取 anchor（from/to 单元格）→ 与覆盖到的 region **同组**；图文件写入 `media_assets`。  
5. Chart：优先导出为派生 PNG（若渲染器可得），否则 `skipped_chart` 写入摄取报告（不静默）。  

**成组扩展：**

- 命中某 region → 返回该 region 全部图 + 表文本；邻接 region 默认不扩（避免整册 Excel）。  
- 可选：同 sheet 内命中行邻近 ±N 行文本窗口（配置项）。

**配额：** `max_xlsx_sheets`、`max_xlsx_rows_per_region`、`max_embedded_images`。

---

## 5. 业界实践 → 映射

| 实践 | PPTX | DOCX | XLSX |
|------|------|------|------|
| 结构感知切分 | slide | heading/section | sheet/region |
| Parent–Child | 页文本召回 → 章窗扩展 | 段落召回 → section/步骤组 | 单元格/行召回 → region |
| 图文绑定 | slide_render 与页文本同组 | 图与前后段落/表同组 | 图与 anchor 单元格同 region |
| 检索与生成解耦 | 文本检索，组装附 media | 同左 | 同左 |
| 向量只存 ID | 共用现有 Milvus schema | 同左 | 同左 |

暂缓 ColPali 多向量。

---

## 6. 数据模型增量（三格式共用）

### 6.1 `knowledge_media_assets`

- `asset_kind`: `slide_render` | `embedded` | `sheet_chart_render` | `thumb`
- `locator` 结构化字段（可 JSON 或列）：`slide_no?`, `sheet_name?`, `cell_anchor?`, `section_path?`
- `object_key`、`sha256`、`width`/`height`、`ordinal_in_group`

### 6.2 `knowledge_evidence_groups`

- `kind`: `chapter` | `section` | `procedure_step` | `table_region` | `window`
- `title`, `expand_default`, 范围字段（slide_start/end 或 sheet+region_id）

### 6.3 `knowledge_chunks` 扩展

- `group_id`, `format_profile`
- `slide_no?` / `sheet_name?` / `section_path?` / `step_label?` / `cell_anchor?`
- `page_kind` / `block_kind`（`slide_text|section_text|table|caption|ocr`）
- `citation_anchor` 示例：  
  - PPTX: `slide-10` / `slide-10:1-2`  
  - DOCX: `section-3.1` / `step-2`  
  - XLSX: `sheet-Orders!R1:R40`

### 6.4 `knowledge_document_versions` 扩展

- `extractor_name/version`, `format_profile`
- `slide_count?`, `sheet_count?`, `section_count?`, `media_count`, `skipped_media_count`

### 6.5 Evidence

`media_refs: [{ asset_id, ordinal, kind, locator }]`；向量 payload 仍不含图与 key。

---

## 7. 成组召回（统一入口，按 group.kind 分支）

```text
命中 chunks → 映射 group → expand(group.kind)：
  chapter/window (pptx): ≤3 全取 else ±1；diagram + 下一 table
  section / procedure_step (docx): 同组全部 media + 邻接 step ±1
  table_region (xlsx): 同 region 文本 + 全部锚定图
→ 预算 max_groups / max_units / max_media → EvidenceBundle
```

`max_units` 统一指「证据页/节/区域」数（PPT 的 slide、Word 的 section 片段、Excel 的 region）。

---

## 8. 模块改造清单

| 模块 | 动作 |
|------|------|
| `ingestion_validation.py` | MIME：pptx / xlsx；docx 保持并加强 OOXML 校验；分格式体积/页数/行数上限 |
| `extraction/port.py` | `KnowledgeContentExtractorPort` → `ExtractedDocument` |
| `extraction/pptx.py` | 新增 |
| `extraction/docx.py` | **替换**仅 paragraphs 的逻辑 |
| `extraction/xlsx.py` | 新增 |
| `extraction/text_pdf.py` | 包装现有 pdf/md/txt |
| `SlideRendererPort` / 可选 `ChartRenderPort` | PPT 整页；XLSX chart 可选 |
| `ingestion_worker.py` | 按 `ExtractedDocument` 写 chunk/media/group |
| `chunking.py` | 按 `format_profile` 分支；Office 不用整文件字符乱切 |
| `runtime_*` | 统一 expand + `media_refs` |
| citation + media 路由 | 授权二进制预览 |
| `pyproject.toml` | 增加 `python-pptx`、`openpyxl` |
| Frontend | 上传三格式；结果按 locator 展示图组 |
| 标准 / ADR | 更新 §4.3 |

---

## 9. 交付切片（含 Word / Excel）

| 切片 | 范围 | DoD |
|------|------|-----|
| **M1 契约** | 迁移 media/group/locator 字段；Port；旧 pdf/md/txt/**现有 docx 文本路径**零回归 | RLS + 回归绿 |
| **M2a PPTX** | 校验 + PptxExtractor + slide_render | Mytrina 64 页可预览可搜；S3 有图 |
| **M2b DOCX** | DocxExtractor：表 + 内嵌图 + section/步骤组 | ✅ |
| **M2c XLSX** | XlsxExtractor：region + 锚定图 + 摄取报告 skipped_chart | ✅ |
| **M3 成组召回** | 统一 expand（三 kind）+ EvidenceBundle | ✅ PPTX/DOCX/XLSX |
| **M4 展示与评测** | 管理台/引用 UI；A/B/C 用例；multimodal config 挂点可空 | ✅ 人可看有序图（检索结果 + Agent 测试展开行）；多模态 Embedding 表单项预留禁用 |

建议实施顺序：**M1 → M2a → M3（先打通 PPTX 闭环）→ M2b → M2c → M4**。  
Word/Excel 与 PPTX **共用 M1 契约**，不另起一套表。

---

## 10. 验收用例

### PPTX（Mytrina）

| ID | 场景 | 期望 |
|----|------|------|
| P1 | 上传 Operation V1.0.pptx | 64 slides；每页 slide_render |
| P2 | 搜 SSO / Sign in | Login 多页有序图 |
| P3 | 搜 Architecture Blueprint | S3 整页图；宜含下一表页 |
| P4 | 搜 Contract column configuration | 步骤页；非整章 20 页 |

### DOCX

| ID | 场景 | 期望 |
|----|------|------|
| W1 | 上传含表 + 多张步骤截图的操作说明 docx | 表可检索；图入 media；步骤成组 |
| W2 | 搜某按钮文案 | 命中步骤文本 + 返回该步上下相关图 |
| W3 | 旧「纯段落」docx | 行为不弱于今日（回归） |

### XLSX

| ID | 场景 | 期望 |
|----|------|------|
| X1 | 上传含说明列 + 浮动示意图的 sheet | region 切分；图与区域绑定 |
| X2 | 搜表头/单元格关键词 | 命中对应 region；返回区内图 |
| X3 | 含 chart 的 sheet | 要么有 chart_render，要么摄取报告明确 skipped |

### 通用

| ID | 场景 | 期望 |
|----|------|------|
| G1 | 引用展开 | 固定 version + locator；可预览 media |
| G2 | 无 Embedding | 仅 FTS 仍可命中并回图组 |

---

## 11. 配置草案

```toml
[knowledge]
max_upload_bytes = 52428800
max_pptx_slides = 200
max_docx_embedded_images = 200
max_xlsx_sheets = 50
max_xlsx_rows_per_region = 2000
max_embedded_images_per_version = 500
slide_render_enabled = true
evidence_max_groups = 6
evidence_max_units = 8
evidence_max_media = 8
evidence_adjacent_window = 1
```

空间级：现有 `embedding_config_id`；预留 `multimodal_embedding_config_id`。

---

## 12. 默认产品决策

| 项 | 默认 |
|----|------|
| PPTX 成组 | 章内 ±1；≤3 整段；diagram + 下页表 |
| DOCX 成组 | 同步骤/同 section 多图一起；邻接 step ±1 |
| XLSX 成组 | 同 table_region 全图；默认不跨 region |
| 对话出图目标（待 R0–R2） | IM/Agent 出站挂结构化 `media`（每 citation 优先 1 张 primary）；完整图组在展开；图字节不进 LLM |
| Agent 回答目标（待 R0–R2） | **图文**：文本 + 可解析 citation 锚点 + 授权媒体附件（见 `docs/knowledge-agent-rich-response-plan.md`） |
| 多手册同空间 | 允许；证据带来源文件名；多库绑定为正常场景 |

---

## 13. 明确不做（本阶段）

- 恶意文件专项（后期审计）  
- 图进向量库 / ColPali  
- 默认多图灌进 LLM  
- EMF/WDP/SmartArt 完美矢量还原（依赖 slide_render 或 skipped 报告）  
- 绑定某家多模态云  

---

## 14. 工程顺序

1. 评审本文件（含 DOCX/XLSX）→ 锁定 §12  
2. **M1** → **M2a + M3**（PPTX 闭环）→ **M2b DOCX** → **M2c XLSX** → **M4**  
3. 多模态 embedding 就绪后只接检索，不改 Evidence Group 契约  
