from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from starlette import status

from app.core.errors import AppError


def normalize_document_title(value: str) -> str:
    return " ".join(value.strip().split()).lower()


def available_title_error() -> AppError:
    return AppError(
        "KNOWLEDGE_DOCUMENT_TITLE_CONFLICT",
        "An available knowledge document with this title already exists in the space",
        status.HTTP_409_CONFLICT,
    )


def is_available_title_conflict(error: IntegrityError) -> bool:
    diagnostic = getattr(error.orig, "diag", None)
    return getattr(diagnostic, "constraint_name", None) == "uq_knowledge_document_available_title"
