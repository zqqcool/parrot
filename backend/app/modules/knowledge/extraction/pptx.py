from __future__ import annotations

import io
import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.slide import Slide

from app.modules.knowledge.extraction.types import (
    ExtractedBlock,
    ExtractedDocument,
    ExtractedGroup,
    ExtractedMedia,
    PageKind,
)
from app.modules.knowledge.extractor import KnowledgeExtractionError

_EXTRACTOR_VERSION = "1"
_PPTX_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


@dataclass(frozen=True)
class _SlideInfo:
    slide_no: int
    title: str
    step_label: str | None
    index_text: str
    page_kind: PageKind
    embedded: tuple[tuple[bytes, str], ...]


class PptxDocumentExtractor:
    """Structure-aware PPTX extractor: one slide → index text + chapter groups."""

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
        del max_pdf_pages, max_sheets, max_rows_per_region
        if content_type != _PPTX_TYPE and not content_type.endswith("presentationml.presentation"):
            raise KnowledgeExtractionError("KNOWLEDGE_FILE_TYPE_INVALID")
        try:
            presentation = Presentation(io.BytesIO(content))
        except Exception as error:
            raise KnowledgeExtractionError("KNOWLEDGE_PPTX_EXTRACTION_FAILED") from error
        slide_count = len(presentation.slides)
        if slide_count == 0:
            raise KnowledgeExtractionError("KNOWLEDGE_DOCUMENT_EMPTY")
        if slide_count > max_slides:
            raise KnowledgeExtractionError("KNOWLEDGE_PPTX_SLIDE_LIMIT")

        slides = tuple(
            _slide_info(index, slide) for index, slide in enumerate(presentation.slides, start=1)
        )
        total_chars = sum(len(item.index_text) for item in slides)
        if total_chars > max_chars:
            raise KnowledgeExtractionError("KNOWLEDGE_EXTRACTED_TEXT_TOO_LARGE")
        if total_chars == 0 and not any(item.embedded for item in slides):
            raise KnowledgeExtractionError("KNOWLEDGE_DOCUMENT_EMPTY")

        group_members = _chapter_members(slides)
        group_by_slide = {
            slide_no: key for key, members in group_members.items() for slide_no in members
        }
        title_by_key = {
            key: next(item.title for item in slides if item.slide_no == members[0])
            for key, members in group_members.items()
        }
        blocks = tuple(
            ExtractedBlock(
                index_text=item.index_text or f"Slide {item.slide_no}",
                block_kind="slide_text",
                page_kind=item.page_kind,
                slide_no=item.slide_no,
                step_label=item.step_label,
                group_key=group_by_slide.get(item.slide_no),
                citation_anchor=f"slide-{item.slide_no}",
            )
            for item in slides
        )
        media_budget = max_embedded_images
        media_items: list[ExtractedMedia] = []
        skipped_media = 0
        for item in slides:
            for ordinal, (blob, content_type) in enumerate(item.embedded, start=1):
                if media_budget <= 0:
                    skipped_media += 1
                    continue
                media_budget -= 1
                media_items.append(
                    ExtractedMedia(
                        asset_kind="embedded",
                        content=blob,
                        content_type=content_type,
                        slide_no=item.slide_no,
                        group_key=group_by_slide.get(item.slide_no),
                        ordinal_in_group=ordinal,
                    )
                )
        return ExtractedDocument(
            format_profile="pptx",
            extractor_name="pptx_document",
            extractor_version=_EXTRACTOR_VERSION,
            blocks=blocks,
            groups=tuple(
                ExtractedGroup(
                    key=key,
                    kind="chapter",
                    title=title_by_key[key],
                    expand_default="adjacent_1",
                    ordinal_start=min(members),
                    ordinal_end=max(members),
                )
                for key, members in group_members.items()
            ),
            media=tuple(media_items),
            slide_count=len(slides),
            skipped_media_count=skipped_media,
            canonical_text="\n\n".join(block.index_text for block in blocks),
        )


def _slide_info(slide_no: int, slide: Slide) -> _SlideInfo:
    title = _slide_title(slide)
    body_parts: list[str] = []
    table_parts: list[str] = []
    embedded: list[tuple[bytes, str]] = []
    autoshapes = 0
    connectors = 0
    for shape in _iter_shapes(slide.shapes):
        shape_type = shape.shape_type
        if shape_type == MSO_SHAPE_TYPE.PICTURE:
            image = getattr(shape, "image", None)
            blob = getattr(image, "blob", None)
            if isinstance(blob, bytes):
                content_type = str(
                    getattr(image, "content_type", None) or _content_type_guess(blob)
                )
                embedded.append((blob, content_type))
            continue
        if shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE:
            autoshapes += 1
        if shape_type == MSO_SHAPE_TYPE.LINE:
            connectors += 1
        if bool(getattr(shape, "has_table", False)):
            table_parts.append(_table_text(shape))
            continue
        if bool(getattr(shape, "has_text_frame", False)):
            text = _shape_text(shape)
            if text and text != title:
                body_parts.append(text)
    notes = _notes_text(slide)
    step_label = _step_label(body_parts)
    ordered = _unique([title, step_label or "", *body_parts, *table_parts, notes])
    return _SlideInfo(
        slide_no=slide_no,
        title=title or f"Slide {slide_no}",
        step_label=step_label,
        index_text="\n".join(ordered),
        page_kind=_page_kind(title, ordered, embedded, autoshapes, connectors, table_parts),
        embedded=tuple(embedded),
    )


def _iter_shapes(shapes: Any) -> Iterator[Any]:
    for shape in shapes:
        if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
            yield from _iter_shapes(shape.shapes)
        else:
            yield shape


def _slide_title(slide: Slide) -> str:
    title_shape = slide.shapes.title
    if title_shape is not None and bool(getattr(title_shape, "has_text_frame", False)):
        text = _shape_text(title_shape)
        if text:
            return re.sub(r"\s+", " ", text)
    for shape in slide.shapes:
        if not bool(getattr(shape, "has_text_frame", False)):
            continue
        if not bool(getattr(shape, "is_placeholder", False)):
            continue
        try:
            ph_type = str(shape.placeholder_format.type)
        except Exception:
            continue
        if "TITLE" in ph_type.upper():
            text = _shape_text(shape)
            if text:
                return re.sub(r"\s+", " ", text)
    return ""


def _shape_text(shape: Any) -> str:
    frame = getattr(shape, "text_frame", None)
    if frame is None:
        return ""
    parts: list[str] = []
    for paragraph in frame.paragraphs:
        value = str(getattr(paragraph, "text", "") or "").strip()
        if value:
            parts.append(value)
    return "\n".join(parts)


def _notes_text(slide: Slide) -> str:
    if not slide.has_notes_slide:
        return ""
    frame = slide.notes_slide.notes_text_frame
    if frame is None:
        return ""
    parts: list[str] = []
    for paragraph in frame.paragraphs:
        value = str(getattr(paragraph, "text", "") or "").strip()
        if value:
            parts.append(value)
    return "\n".join(parts)


def _table_text(shape: Any) -> str:
    table = shape.table
    rows: list[str] = []
    for row in table.rows:
        cells = [
            str(cell.text).strip().replace("\n", " ")
            for cell in row.cells
            if str(cell.text).strip()
        ]
        if cells:
            rows.append(" | ".join(cells))
    return "\n".join(rows)


def _step_label(body_parts: list[str]) -> str | None:
    for part in body_parts[:3]:
        first = part.split("\n", 1)[0]
        if re.match(r"^\d+(\.\d+)*\s+\S+", first) or re.match(r"^\d+-\d+\b", first):
            return first[:191]
    return None


def _page_kind(
    title: str,
    ordered: list[str],
    embedded: list[tuple[bytes, str]],
    autoshapes: int,
    connectors: int,
    table_parts: list[str],
) -> PageKind:
    chars = sum(len(part) for part in ordered)
    if title.lower().startswith("version") and table_parts:
        return "table"
    if autoshapes + connectors >= 15 and not embedded:
        return "diagram"
    if table_parts and chars > 200:
        return "table"
    if embedded and chars < 80:
        return "cover"
    if embedded:
        return "operation"
    return "unknown"


def _chapter_members(slides: tuple[_SlideInfo, ...]) -> dict[str, list[int]]:
    groups: dict[str, list[int]] = {}
    current_title: str | None = None
    current_key: str | None = None
    run = 0
    for item in slides:
        normalized = re.sub(r"\s+", " ", item.title).strip().lower()
        if current_title != normalized:
            run += 1
            current_title = normalized
            current_key = f"chapter:{run}"
            groups[current_key] = []
        assert current_key is not None
        groups[current_key].append(item.slide_no)
    return groups


def _unique(parts: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for part in parts:
        value = part.strip()
        if not value or value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _content_type_guess(blob: bytes) -> str:
    if blob.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if blob.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    return "application/octet-stream"
