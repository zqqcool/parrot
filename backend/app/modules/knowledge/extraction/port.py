from __future__ import annotations

from typing import Protocol

from app.modules.knowledge.extraction.types import ExtractedDocument


class KnowledgeContentExtractorPort(Protocol):
    """Format-specific extractor; workers consume only ExtractedDocument."""

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
    ) -> ExtractedDocument: ...
