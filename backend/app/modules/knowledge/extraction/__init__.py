from __future__ import annotations

from app.modules.knowledge.extraction.docx import DocxDocumentExtractor
from app.modules.knowledge.extraction.port import KnowledgeContentExtractorPort
from app.modules.knowledge.extraction.registry import (
    CompositeKnowledgeExtractor,
    default_knowledge_extractor,
)
from app.modules.knowledge.extraction.text_document import (
    PlainTextDocumentExtractor,
    extract_legacy_document,
)
from app.modules.knowledge.extraction.types import (
    ExtractedBlock,
    ExtractedDocument,
    ExtractedGroup,
    ExtractedMedia,
)
from app.modules.knowledge.extraction.xlsx import XlsxDocumentExtractor

__all__ = [
    "CompositeKnowledgeExtractor",
    "DocxDocumentExtractor",
    "ExtractedBlock",
    "ExtractedDocument",
    "ExtractedGroup",
    "ExtractedMedia",
    "KnowledgeContentExtractorPort",
    "PlainTextDocumentExtractor",
    "XlsxDocumentExtractor",
    "default_knowledge_extractor",
    "extract_legacy_document",
]
