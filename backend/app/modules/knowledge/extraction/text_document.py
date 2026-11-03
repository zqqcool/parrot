from __future__ import annotations

from app.modules.knowledge.extraction.types import (
    ExtractedBlock,
    ExtractedDocument,
    FormatProfile,
)
from app.modules.knowledge.extractor import KnowledgeExtractionError, extract_text

_EXTRACTOR_VERSION = "1"


class PlainTextDocumentExtractor:
    """Adapter over the legacy text/PDF/DOCX paragraph extractor."""

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
        del max_slides, max_embedded_images, max_sheets, max_rows_per_region
        text = extract_text(content, content_type, max_chars, max_pdf_pages)
        profile = _profile_for(content_type)
        return ExtractedDocument(
            format_profile=profile,
            extractor_name="plain_text_document",
            extractor_version=_EXTRACTOR_VERSION,
            blocks=(
                ExtractedBlock(
                    index_text=text,
                    block_kind="plain" if profile != "docx" else "section_text",
                    citation_anchor="chunk-body",
                ),
            ),
            canonical_text=text,
        )


def _profile_for(content_type: str) -> FormatProfile:
    if content_type == "application/pdf":
        return "pdf"
    if content_type.endswith("wordprocessingml.document"):
        return "docx"
    return "plain_text"


def extract_legacy_document(
    content: bytes,
    content_type: str,
    *,
    max_chars: int,
    max_pdf_pages: int,
    max_slides: int = 200,
) -> ExtractedDocument:
    return PlainTextDocumentExtractor().extract(
        content,
        content_type,
        max_chars=max_chars,
        max_pdf_pages=max_pdf_pages,
        max_slides=max_slides,
    )


__all__ = [
    "KnowledgeExtractionError",
    "PlainTextDocumentExtractor",
    "extract_legacy_document",
]
