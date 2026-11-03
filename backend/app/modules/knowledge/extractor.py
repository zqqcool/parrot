from __future__ import annotations

from io import BytesIO

from docx import Document
from pypdf import PdfReader


class KnowledgeExtractionError(ValueError):
    pass


def extract_text(content: bytes, content_type: str, max_chars: int, max_pdf_pages: int) -> str:
    if content_type in {"text/plain", "text/markdown"}:
        return _bounded_text(content.decode("utf-8", errors="strict"), max_chars)
    if content_type == "application/pdf":
        return _pdf_text(content, max_chars, max_pdf_pages)
    if content_type.endswith("wordprocessingml.document"):
        return _docx_text(content, max_chars)
    raise KnowledgeExtractionError("KNOWLEDGE_FILE_TYPE_INVALID")


def _pdf_text(content: bytes, max_chars: int, max_pages: int) -> str:
    try:
        reader = PdfReader(BytesIO(content), strict=True)
        if len(reader.pages) > max_pages:
            raise KnowledgeExtractionError("KNOWLEDGE_PDF_PAGE_LIMIT")
        extracted = "\n\n".join(page.extract_text() or "" for page in reader.pages)
        return _bounded_text(extracted, max_chars)
    except KnowledgeExtractionError:
        raise
    except Exception as error:
        raise KnowledgeExtractionError("KNOWLEDGE_PDF_EXTRACTION_FAILED") from error


def _docx_text(content: bytes, max_chars: int) -> str:
    try:
        document = Document(BytesIO(content))
        return _bounded_text("\n\n".join(item.text for item in document.paragraphs), max_chars)
    except Exception as error:
        raise KnowledgeExtractionError("KNOWLEDGE_DOCX_EXTRACTION_FAILED") from error


def _bounded_text(value: str, maximum: int) -> str:
    normalized = "\n".join(
        line.rstrip() for line in value.replace("\r\n", "\n").split("\n")
    ).strip()
    if not normalized:
        raise KnowledgeExtractionError("KNOWLEDGE_DOCUMENT_EMPTY")
    if len(normalized) > maximum:
        raise KnowledgeExtractionError("KNOWLEDGE_EXTRACTED_TEXT_TOO_LARGE")
    return normalized
