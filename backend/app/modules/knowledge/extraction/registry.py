from __future__ import annotations

from app.modules.knowledge.extraction.docx import DocxDocumentExtractor
from app.modules.knowledge.extraction.port import KnowledgeContentExtractorPort
from app.modules.knowledge.extraction.pptx import PptxDocumentExtractor
from app.modules.knowledge.extraction.text_document import PlainTextDocumentExtractor
from app.modules.knowledge.extraction.types import ExtractedDocument
from app.modules.knowledge.extraction.xlsx import XlsxDocumentExtractor
from app.modules.knowledge.extractor import KnowledgeExtractionError

_PLAIN = PlainTextDocumentExtractor()
_PPTX = PptxDocumentExtractor()
_DOCX = DocxDocumentExtractor()
_XLSX = XlsxDocumentExtractor()
_PPTX_TYPES = {
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}
_XLSX_TYPES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
_DOCX_TYPES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
_LEGACY_TYPES = {
    "application/pdf",
    "text/markdown",
    "text/plain",
}


class CompositeKnowledgeExtractor:
    """Routes by MIME to format-specific extractors."""

    def __init__(
        self,
        *,
        pptx: KnowledgeContentExtractorPort | None = None,
        xlsx: KnowledgeContentExtractorPort | None = None,
        docx_structured: KnowledgeContentExtractorPort | None = None,
        plain: KnowledgeContentExtractorPort | None = None,
    ) -> None:
        self._pptx = pptx if pptx is not None else _PPTX
        self._xlsx = xlsx if xlsx is not None else _XLSX
        self._docx = docx_structured if docx_structured is not None else _DOCX
        self._plain = plain or _PLAIN

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
        normalized = content_type.lower().split(";", 1)[0].strip()
        limits = {
            "max_chars": max_chars,
            "max_pdf_pages": max_pdf_pages,
            "max_slides": max_slides,
            "max_embedded_images": max_embedded_images,
            "max_sheets": max_sheets,
            "max_rows_per_region": max_rows_per_region,
        }
        if normalized in _PPTX_TYPES:
            return self._pptx.extract(content, normalized, **limits)
        if normalized in _XLSX_TYPES:
            return self._xlsx.extract(content, normalized, **limits)
        if normalized in _DOCX_TYPES:
            return self._docx.extract(content, normalized, **limits)
        if normalized not in _LEGACY_TYPES:
            raise KnowledgeExtractionError("KNOWLEDGE_FILE_TYPE_INVALID")
        return self._plain.extract(content, normalized, **limits)


def default_knowledge_extractor() -> CompositeKnowledgeExtractor:
    return CompositeKnowledgeExtractor()
