from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

FormatProfile = Literal["plain_text", "pptx", "docx", "xlsx", "pdf"]
PageKind = Literal["cover", "table", "diagram", "operation", "section", "sheet", "unknown"]
BlockKind = Literal["slide_text", "section_text", "table", "caption", "ocr", "plain"]
GroupKind = Literal["chapter", "section", "procedure_step", "table_region", "window"]
AssetKind = Literal["slide_render", "embedded", "sheet_chart_render", "thumb"]


@dataclass(frozen=True)
class ExtractedMedia:
    """Binary media produced by an extractor before object-storage persistence."""

    asset_kind: AssetKind
    content: bytes
    content_type: str
    slide_no: int | None = None
    sheet_name: str | None = None
    cell_anchor: str | None = None
    section_path: str | None = None
    group_key: str | None = None
    ordinal_in_group: int = 0
    width: int | None = None
    height: int | None = None


@dataclass(frozen=True)
class ExtractedBlock:
    """One indexable text unit with optional structural locators."""

    index_text: str
    block_kind: BlockKind = "plain"
    page_kind: PageKind = "unknown"
    slide_no: int | None = None
    sheet_name: str | None = None
    section_path: str | None = None
    step_label: str | None = None
    cell_anchor: str | None = None
    group_key: str | None = None
    citation_anchor: str | None = None


@dataclass(frozen=True)
class ExtractedGroup:
    key: str
    kind: GroupKind
    title: str
    expand_default: str = "adjacent_1"
    ordinal_start: int = 0
    ordinal_end: int = 0


@dataclass(frozen=True)
class ExtractedDocument:
    format_profile: FormatProfile
    extractor_name: str
    extractor_version: str
    blocks: tuple[ExtractedBlock, ...]
    groups: tuple[ExtractedGroup, ...] = ()
    media: tuple[ExtractedMedia, ...] = ()
    slide_count: int = 0
    sheet_count: int = 0
    section_count: int = 0
    skipped_media_count: int = 0
    canonical_text: str = ""
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def joined_index_text(self) -> str:
        if self.canonical_text:
            return self.canonical_text
        return "\n\n".join(block.index_text for block in self.blocks if block.index_text.strip())
