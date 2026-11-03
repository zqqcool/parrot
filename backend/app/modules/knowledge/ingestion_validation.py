from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from pathlib import PurePath

from starlette import status

from app.core.errors import AppError

ALLOWED_CONTENT_TYPES = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "text/markdown": ".md",
    "text/plain": ".txt",
}


@dataclass(frozen=True)
class KnowledgeFile:
    content_type: str
    extension: str


def validate_declared_file(
    content_type: str, filename: str, size_bytes: int, maximum: int
) -> KnowledgeFile:
    normalized = content_type.lower().split(";", 1)[0].strip()
    extension = ALLOWED_CONTENT_TYPES.get(normalized)
    if extension is None or PurePath(filename).suffix.lower() != extension:
        raise AppError(
            "KNOWLEDGE_FILE_TYPE_INVALID",
            "Knowledge file type is not supported",
            status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    if size_bytes > maximum:
        raise AppError(
            "KNOWLEDGE_FILE_TOO_LARGE",
            "Knowledge file exceeds the configured size limit",
            status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    return KnowledgeFile(normalized, extension)


def validate_uploaded_file(
    content: bytes, content_type: str, filename: str, maximum: int
) -> KnowledgeFile:
    item = validate_declared_file(content_type, filename, len(content), maximum)
    if item.content_type == "application/pdf" and not content.startswith(b"%PDF-"):
        _reject_content()
    if item.content_type.endswith(
        ("wordprocessingml.document", "presentationml.presentation", "spreadsheetml.sheet")
    ) and not _valid_ooxml_package(content, item.content_type):
        _reject_content()
    if item.content_type.startswith("text/") and b"\x00" in content:
        _reject_content()
    return item


def _reject_content() -> None:
    raise AppError(
        "KNOWLEDGE_FILE_CONTENT_INVALID",
        "Knowledge file content does not match its declared type",
        status.HTTP_422_UNPROCESSABLE_CONTENT,
    )


def _valid_ooxml_package(content: bytes, content_type: str) -> bool:
    marker_by_type = {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": (
            "word/document.xml"
        ),
        "application/vnd.openxmlformats-officedocument.presentationml.presentation": (
            "ppt/presentation.xml"
        ),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xl/workbook.xml",
    }
    marker = marker_by_type.get(content_type)
    if marker is None or not content.startswith(b"PK"):
        return False
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            names = set(archive.namelist())
    except (OSError, zipfile.BadZipFile):
        return False
    return "[Content_Types].xml" in names and marker in names
