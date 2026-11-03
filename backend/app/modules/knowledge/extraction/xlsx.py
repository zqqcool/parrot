from __future__ import annotations

import io
import re
from dataclasses import dataclass
from typing import Any

from openpyxl import load_workbook
from openpyxl.drawing.image import Image as OpenpyxlImage
from openpyxl.worksheet.worksheet import Worksheet

from app.modules.knowledge.extraction.types import (
    ExtractedBlock,
    ExtractedDocument,
    ExtractedGroup,
    ExtractedMedia,
)
from app.modules.knowledge.extractor import KnowledgeExtractionError

_EXTRACTOR_VERSION = "1"
_XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_CELL_RE = re.compile(r"^([A-Z]+)([0-9]+)$")


@dataclass(frozen=True)
class _Region:
    sheet_name: str
    start_row: int
    end_row: int
    start_col: int
    end_col: int

    @property
    def key(self) -> str:
        return f"sheet:{self.sheet_name}:R{self.start_row}-{self.end_row}"

    @property
    def cell_anchor(self) -> str:
        return f"{self.sheet_name}!R{self.start_row}:R{self.end_row}"


class XlsxDocumentExtractor:
    """Structure-aware XLSX extractor: sheet regions + anchored images."""

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
        del max_pdf_pages, max_slides
        if content_type != _XLSX_TYPE and not content_type.endswith("spreadsheetml.sheet"):
            raise KnowledgeExtractionError("KNOWLEDGE_FILE_TYPE_INVALID")
        try:
            workbook = load_workbook(io.BytesIO(content), data_only=True, read_only=False)
        except Exception as error:
            raise KnowledgeExtractionError("KNOWLEDGE_XLSX_EXTRACTION_FAILED") from error

        try:
            return _extract_workbook(
                workbook,
                max_chars=max_chars,
                max_sheets=max_sheets,
                max_rows_per_region=max_rows_per_region,
                max_embedded_images=max_embedded_images,
            )
        finally:
            workbook.close()


def _extract_workbook(
    workbook: Any,
    *,
    max_chars: int,
    max_sheets: int,
    max_rows_per_region: int,
    max_embedded_images: int,
) -> ExtractedDocument:
    if len(workbook.sheetnames) > max_sheets:
        raise KnowledgeExtractionError("KNOWLEDGE_XLSX_SHEET_LIMIT")
    blocks: list[ExtractedBlock] = []
    media: list[ExtractedMedia] = []
    groups: list[ExtractedGroup] = []
    skipped_media = 0
    skipped_charts = 0
    char_budget = max_chars
    for sheet_name in workbook.sheetnames:
        sheet = workbook[sheet_name]
        skipped_charts += len(getattr(sheet, "_charts", ()) or ())
        regions = _table_regions(sheet, max_rows_per_region)
        if not regions:
            continue
        sheet_media, sheet_skipped = _sheet_images(
            sheet,
            sheet_name=sheet_name,
            regions=regions,
            max_embedded_images=max_embedded_images,
            current_count=len(media),
        )
        media.extend(sheet_media)
        skipped_media += sheet_skipped
        char_budget, _added = _append_region_blocks(
            sheet,
            regions=regions,
            blocks=blocks,
            groups=groups,
            char_budget=char_budget,
        )
    if not blocks:
        raise KnowledgeExtractionError("KNOWLEDGE_DOCUMENT_EMPTY")
    return ExtractedDocument(
        format_profile="xlsx",
        extractor_name="xlsx_document",
        extractor_version=_EXTRACTOR_VERSION,
        blocks=tuple(blocks),
        groups=tuple(groups),
        media=tuple(media),
        sheet_count=len(workbook.sheetnames),
        skipped_media_count=skipped_media + skipped_charts,
        warnings=("charts_skipped",) if skipped_charts else (),
    )


def _append_region_blocks(
    sheet: Worksheet,
    *,
    regions: list[_Region],
    blocks: list[ExtractedBlock],
    groups: list[ExtractedGroup],
    char_budget: int,
) -> tuple[int, int]:
    added = 0
    for region in regions:
        text = _region_text(sheet, region)
        if not text.strip():
            continue
        if len(text) > char_budget:
            raise KnowledgeExtractionError("KNOWLEDGE_EXTRACTED_TEXT_TOO_LARGE")
        piece = text
        char_budget -= len(piece)
        groups.append(
            ExtractedGroup(
                key=region.key,
                kind="table_region",
                title=f"{region.sheet_name} R{region.start_row}-{region.end_row}",
                expand_default="group_media",
                ordinal_start=len(blocks) + 1,
                ordinal_end=len(blocks) + 1,
            )
        )
        blocks.append(
            ExtractedBlock(
                index_text=piece,
                block_kind="table",
                page_kind="sheet",
                sheet_name=region.sheet_name,
                cell_anchor=region.cell_anchor,
                group_key=region.key,
                citation_anchor=region.cell_anchor,
            )
        )
        added += 1
    return char_budget, added


def _table_regions(sheet: Worksheet, max_rows: int) -> list[_Region]:
    max_row = int(sheet.max_row or 0)
    max_column = int(sheet.max_column or 0)
    if max_row <= 0 or max_column <= 0:
        return []
    used_rows = [
        row
        for row in range(1, max_row + 1)
        if any(
            _cell_text(sheet.cell(row=row, column=col).value) for col in range(1, max_column + 1)
        )
    ]
    if not used_rows:
        return []
    regions: list[_Region] = []
    start = used_rows[0]
    prev = used_rows[0]
    for row in used_rows[1:]:
        if row == prev + 1 and (row - start + 1) <= max_rows:
            prev = row
            continue
        regions.append(_region_bounds(sheet, start, prev))
        start = row
        prev = row
    regions.append(_region_bounds(sheet, start, prev))
    return regions


def _region_bounds(sheet: Worksheet, start_row: int, end_row: int) -> _Region:
    max_col = sheet.max_column or 1
    used_cols = [
        col
        for col in range(1, max_col + 1)
        if any(
            _cell_text(sheet.cell(row=row, column=col).value)
            for row in range(start_row, end_row + 1)
        )
    ]
    start_col = used_cols[0] if used_cols else 1
    end_col = used_cols[-1] if used_cols else 1
    return _Region(
        sheet_name=sheet.title,
        start_row=start_row,
        end_row=end_row,
        start_col=start_col,
        end_col=end_col,
    )


def _region_text(sheet: Worksheet, region: _Region) -> str:
    lines = [f"Sheet: {region.sheet_name}"]
    for row in range(region.start_row, region.end_row + 1):
        values = [
            _cell_text(sheet.cell(row=row, column=col).value)
            for col in range(region.start_col, region.end_col + 1)
        ]
        if any(values):
            lines.append(" | ".join(values))
    return "\n".join(lines)


def _sheet_images(
    sheet: Worksheet,
    *,
    sheet_name: str,
    regions: list[_Region],
    max_embedded_images: int,
    current_count: int,
) -> tuple[list[ExtractedMedia], int]:
    images: list[ExtractedMedia] = []
    skipped = 0
    for index, image in enumerate(getattr(sheet, "_images", ()) or (), start=1):
        if current_count + len(images) >= max_embedded_images:
            skipped += 1
            continue
        content, content_type = _image_bytes(image)
        if content is None or content_type is None:
            skipped += 1
            continue
        anchor = _image_anchor(image)
        region = _region_for_anchor(regions, anchor)
        group_key = region.key if region else f"sheet:{sheet_name}:unanchored"
        images.append(
            ExtractedMedia(
                asset_kind="embedded",
                content=content,
                content_type=content_type,
                sheet_name=sheet_name,
                cell_anchor=anchor,
                group_key=group_key,
                ordinal_in_group=index,
            )
        )
    return images, skipped


def _image_bytes(image: OpenpyxlImage) -> tuple[bytes | None, str | None]:
    try:
        data_fn = getattr(image, "_data", None)
        if not callable(data_fn):
            return None, None
        raw: Any = data_fn()
        if not isinstance(raw, (bytes, bytearray)):
            return None, None
        content = bytes(raw)
        image_format = str(getattr(image, "format", "") or "").casefold()
        content_type = {
            "gif": "image/gif",
            "jpeg": "image/jpeg",
            "jpg": "image/jpeg",
            "png": "image/png",
        }.get(image_format)
        if content_type is None:
            return None, None
        return content, content_type
    except Exception:
        return None, None


def _image_anchor(image: OpenpyxlImage) -> str | None:
    anchor = getattr(image, "anchor", None)
    if anchor is None:
        return None
    if isinstance(anchor, str):
        return anchor
    marker = getattr(anchor, "_from", None) or getattr(anchor, "from_", None)
    if marker is None:
        return None
    col = getattr(marker, "col", None)
    row = getattr(marker, "row", None)
    if not isinstance(col, int) or not isinstance(row, int):
        return None
    return f"{_col_letter(col + 1)}{row + 1}"


def _region_for_anchor(regions: list[_Region], anchor: str | None) -> _Region | None:
    if not anchor:
        return regions[0] if regions else None
    match = _CELL_RE.match(anchor)
    if not match:
        return regions[0] if regions else None
    row = int(match.group(2))
    for region in regions:
        if region.start_row <= row <= region.end_row:
            return region
    return regions[0] if regions else None


def _col_letter(index: int) -> str:
    value = index
    letters: list[str] = []
    while value:
        value, rem = divmod(value - 1, 26)
        letters.append(chr(65 + rem))
    return "".join(reversed(letters)) or "A"


def _cell_text(value: object) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())
