from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from typing import Any

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.modules.knowledge.extraction.types import (
    ExtractedBlock,
    ExtractedDocument,
    ExtractedGroup,
    ExtractedMedia,
)
from app.modules.knowledge.extractor import KnowledgeExtractionError

_EXTRACTOR_VERSION = "1"
_DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_STEP_RE = re.compile(r"^(?:步骤|step)\s*([0-9]+(?:\.[0-9]+)*)\b", re.IGNORECASE)
_NUMBERED_STEP_RE = re.compile(r"^([0-9]+(?:\.[0-9]+)*)[.)、]\s*\S+")
_HEADING_RE = re.compile(r"^Heading\s+(\d+)$", re.IGNORECASE)


@dataclass
class _SectionState:
    path: list[str] = field(default_factory=lambda: [])
    group_key: str | None = None
    step_label: str | None = None
    media_ordinal: int = 0


class DocxDocumentExtractor:
    """Structure-aware DOCX extractor: sections, tables, embedded images."""

    def extract(
        self,
        content: bytes,
        content_type: str,
        *,
        max_chars: int,
        max_pdf_pages: int,
        max_slides: int,
        max_embedded_images: int = 200,
        max_sheets: int = 50,
        max_rows_per_region: int = 2_000,
    ) -> ExtractedDocument:
        del max_pdf_pages, max_slides, max_sheets, max_rows_per_region
        if content_type != _DOCX_TYPE and not content_type.endswith("wordprocessingml.document"):
            raise KnowledgeExtractionError("KNOWLEDGE_FILE_TYPE_INVALID")
        try:
            document: Any = Document(io.BytesIO(content))
        except Exception as error:
            raise KnowledgeExtractionError("KNOWLEDGE_DOCX_EXTRACTION_FAILED") from error

        blocks: list[ExtractedBlock] = []
        media: list[ExtractedMedia] = []
        groups: dict[str, ExtractedGroup] = {}
        state = _SectionState()
        skipped = 0
        char_budget = max_chars

        for element in document.element.body:
            tag = element.tag
            if tag == qn("w:p"):
                paragraph: Any = Paragraph(element, document)
                char_budget, skipped = _consume_paragraph(
                    paragraph,
                    state=state,
                    blocks=blocks,
                    media=media,
                    groups=groups,
                    char_budget=char_budget,
                    max_embedded_images=max_embedded_images,
                    skipped=skipped,
                )
            elif tag == qn("w:tbl"):
                table: Any = Table(element, document)
                char_budget, skipped = _consume_table(
                    table,
                    state=state,
                    blocks=blocks,
                    media=media,
                    groups=groups,
                    char_budget=char_budget,
                    max_embedded_images=max_embedded_images,
                    skipped=skipped,
                )

        if not blocks:
            raise KnowledgeExtractionError("KNOWLEDGE_DOCUMENT_EMPTY")
        return ExtractedDocument(
            format_profile="docx",
            extractor_name="docx_document",
            extractor_version=_EXTRACTOR_VERSION,
            blocks=tuple(blocks),
            groups=tuple(groups.values()),
            media=tuple(media),
            section_count=sum(1 for group in groups.values() if group.kind == "section"),
            skipped_media_count=skipped,
        )


def _consume_paragraph(
    paragraph: Any,
    *,
    state: _SectionState,
    blocks: list[ExtractedBlock],
    media: list[ExtractedMedia],
    groups: dict[str, ExtractedGroup],
    char_budget: int,
    max_embedded_images: int,
    skipped: int,
) -> tuple[int, int]:
    level = _heading_level(paragraph)
    text = (paragraph.text or "").strip()
    if level is not None and text:
        state.path = [*state.path[: level - 1], text]
        state.group_key = f"section:{'/'.join(state.path)}"
        state.step_label = None
        groups[state.group_key] = ExtractedGroup(
            key=state.group_key,
            kind="section",
            title="/".join(state.path)[:300],
            expand_default="group_media",
            ordinal_start=len(blocks) + 1,
            ordinal_end=len(blocks) + 1,
        )
    step_number = _step_number(text) if level is None else None
    if step_number is not None:
        state.step_label = text.split("\n", 1)[0][:120]
        state.group_key = f"step:{'/'.join(state.path)}:{step_number}"
        groups[state.group_key] = ExtractedGroup(
            key=state.group_key,
            kind="procedure_step",
            title=state.step_label or text[:120],
            expand_default="adjacent_1",
            ordinal_start=len(blocks) + 1,
            ordinal_end=len(blocks) + 1,
        )

    images, image_skipped = _paragraph_images(
        paragraph,
        state=state,
        max_embedded_images=max_embedded_images,
        current_count=len(media),
    )
    media.extend(images)
    skipped += image_skipped

    if not text and not images:
        return char_budget, skipped
    if text:
        piece = _bounded_piece(text, char_budget)
        char_budget -= len(piece)
        _ensure_group(state, groups, blocks)
        section_path = "/".join(state.path) if state.path else None
        blocks.append(
            ExtractedBlock(
                index_text=piece,
                block_kind="section_text",
                page_kind="section",
                section_path=section_path,
                step_label=state.step_label,
                group_key=_group_key(state),
                citation_anchor=_citation_for(state),
            )
        )
    return char_budget, skipped


def _consume_table(
    table: Any,
    *,
    state: _SectionState,
    blocks: list[ExtractedBlock],
    media: list[ExtractedMedia],
    groups: dict[str, ExtractedGroup],
    char_budget: int,
    max_embedded_images: int,
    skipped: int,
) -> tuple[int, int]:
    rows: list[str] = []
    for row in table.rows:
        cells = [" ".join(cell.text.split()) for cell in row.cells]
        if any(cells):
            rows.append("| " + " | ".join(cells) + " |")
    images, image_skipped = _related_images(
        table._element,  # noqa: SLF001
        table.part,
        state=state,
        max_embedded_images=max_embedded_images,
        current_count=len(media),
    )
    skipped += image_skipped
    if not rows and not images:
        return char_budget, skipped
    _ensure_group(state, groups, blocks)
    media.extend(images)
    if not rows:
        return char_budget, skipped
    markdown = "\n".join(rows)
    piece = _bounded_piece(markdown, char_budget)
    char_budget -= len(piece)
    section_path = "/".join(state.path) if state.path else None
    blocks.append(
        ExtractedBlock(
            index_text=piece,
            block_kind="table",
            page_kind="table",
            section_path=section_path,
            step_label=state.step_label,
            group_key=_group_key(state),
            citation_anchor=_citation_for(state, suffix="table"),
        )
    )
    return char_budget, skipped


def _paragraph_images(
    paragraph: Any,
    *,
    state: _SectionState,
    max_embedded_images: int,
    current_count: int,
) -> tuple[list[ExtractedMedia], int]:
    return _related_images(
        paragraph._element,  # noqa: SLF001
        paragraph.part,
        state=state,
        max_embedded_images=max_embedded_images,
        current_count=current_count,
    )


def _related_images(
    element: Any,
    part: Any,
    *,
    state: _SectionState,
    max_embedded_images: int,
    current_count: int,
) -> tuple[list[ExtractedMedia], int]:
    images: list[ExtractedMedia] = []
    skipped = 0
    section_path = "/".join(state.path) if state.path else None
    group_key = _group_key(state)
    for blip in element.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}blip"):
        embed = blip.get(qn("r:embed"))
        if not embed:
            skipped += 1
            continue
        if current_count + len(images) >= max_embedded_images:
            skipped += 1
            continue
        try:
            related = part.related_parts[embed]
            content = related.blob
            content_type = getattr(related, "content_type", "application/octet-stream")
        except Exception:
            skipped += 1
            continue
        if not str(content_type).startswith("image/"):
            skipped += 1
            continue
        state.media_ordinal += 1
        images.append(
            ExtractedMedia(
                asset_kind="embedded",
                content=bytes(content),
                content_type=str(content_type),
                section_path=section_path,
                group_key=group_key,
                ordinal_in_group=state.media_ordinal,
            )
        )
    return images, skipped


def _ensure_group(
    state: _SectionState,
    groups: dict[str, ExtractedGroup],
    blocks: list[ExtractedBlock],
) -> None:
    group_key = _group_key(state)
    section_path = "/".join(state.path) if state.path else None
    if group_key not in groups:
        groups[group_key] = ExtractedGroup(
            key=group_key,
            kind="section" if state.step_label is None else "procedure_step",
            title=(state.step_label or section_path or "Document")[:300],
            expand_default="group_media" if state.step_label is None else "adjacent_1",
            ordinal_start=len(blocks) + 1,
            ordinal_end=len(blocks) + 1,
        )
        return
    group = groups[group_key]
    groups[group_key] = ExtractedGroup(
        key=group.key,
        kind=group.kind,
        title=group.title,
        expand_default=group.expand_default,
        ordinal_start=group.ordinal_start,
        ordinal_end=len(blocks) + 1,
    )


def _group_key(state: _SectionState) -> str:
    if state.group_key:
        return state.group_key
    section_path = "/".join(state.path) if state.path else None
    return f"section:{section_path}" if section_path else "section:body"


def _heading_level(paragraph: Any) -> int | None:
    style_name = getattr(getattr(paragraph, "style", None), "name", "") or ""
    match = _HEADING_RE.match(style_name)
    if match:
        return int(match.group(1))
    return None


def _step_number(value: str) -> str | None:
    match = _STEP_RE.match(value) or _NUMBERED_STEP_RE.match(value)
    return match.group(1) if match else None


def _bounded_piece(value: str, remaining: int) -> str:
    if len(value) > remaining:
        raise KnowledgeExtractionError("KNOWLEDGE_EXTRACTED_TEXT_TOO_LARGE")
    return value


def _citation_for(state: _SectionState, *, suffix: str | None = None) -> str:
    if state.step_label:
        base = f"step-{_slug(state.step_label)}"
    elif state.path:
        base = f"section-{_slug('/'.join(state.path))}"
    else:
        base = "section-body"
    return f"{base}:{suffix}" if suffix else base


def _slug(value: str) -> str:
    cleaned = re.sub(r"\s+", "-", value.strip())[:80]
    return cleaned or "item"
