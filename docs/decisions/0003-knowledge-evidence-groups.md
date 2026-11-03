# ADR 0003: Knowledge Evidence Groups for Office Multimedia

## Status

Accepted on 2026-07-22 (implementation in progress).

## Context

Parrot knowledge ingestion historically flattened documents into character-window chunks.
Operation manuals (especially PPTX) require slide-level units, chapter adjacency for related
screenshots, and authorized preview of images without storing binaries in the vector index.

## Decision

- Introduce `KnowledgeContentExtractorPort` producing `ExtractedDocument` (blocks, groups, media).
- Persist `knowledge_evidence_groups` and `knowledge_media_assets`; extend chunks/versions with
  locators (`slide_no`, `group_id`, `format_profile`, …).
- Vector store payload remains ID-only; originals and renders stay in private object storage.
- PPTX: one slide is one evidence page; same-title adjacent slides form a chapter group; default
  retrieval expand is adjacent ±1 (short chapters may return whole group).
- DOCX/XLSX share the same group/media contract with format-specific extractors.
- Agent tool observations remain text-first (no image bytes in the model context). The planned
  rich-response path attaches media to user-facing answers as structured `output.media` references
  and serves them through authorized citation/media routes (management or interaction-scoped visitor
  access); that outbound path is not implemented yet. See
  `docs/knowledge-agent-rich-response-plan.md` for the staged delivery plan.

## Consequences

- Ingestion workers depend on extractors behind a port; MIME routing is explicit.
- Slide rendering (full-page PNG) is required for shape-only diagrams and lands as `slide_render`
  assets. A missing or failed LibreOffice renderer may create a `thumb` for operator diagnostics,
  but that fallback is not evidence-equivalent and increments `skipped_media_count`.
- Persisted evidence media is limited to browser-safe GIF, JPEG, PNG, and WebP. Unsupported Office
  embedded formats such as WMF or EMF are skipped, increment `skipped_media_count`, and never fail
  the whole document; the full-page slide render remains the visual evidence for that page.
- Media object keys are deterministic. A retry may reuse an existing object only after verifying its
  content hash; a missing or different object remains a hard storage failure.
- Upload-time malware auditing remains a separate future gate; this ADR does not encode threat
  scanning into extractors.
