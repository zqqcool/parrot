from __future__ import annotations

from starlette import status

from app.core.errors import AppError
from app.modules.knowledge.models import KnowledgeDocumentVersion, KnowledgeSpace
from app.modules.knowledge.preprocessing import KnowledgeTextProcessingError, process_content
from app.modules.knowledge.schemas import KnowledgeSpaceView, KnowledgeTextProcessingSettings


def process_manual_content(value: str, space: KnowledgeSpace) -> str:
    try:
        return process_content(
            value,
            normalize_whitespace=bool(getattr(space, "normalize_whitespace", False)),
            remove_urls_and_emails=bool(getattr(space, "remove_urls_and_emails", False)),
        )
    except KnowledgeTextProcessingError as error:
        raise AppError(
            str(error),
            "Knowledge document content is required",
            status.HTTP_422_UNPROCESSABLE_CONTENT,
        ) from error


def text_processing_settings(
    item: KnowledgeSpace | KnowledgeDocumentVersion,
) -> KnowledgeTextProcessingSettings:
    return KnowledgeTextProcessingSettings(
        normalize_whitespace=bool(getattr(item, "normalize_whitespace", False)),
        remove_urls_and_emails=bool(getattr(item, "remove_urls_and_emails", False)),
    )


def knowledge_space_view(item: KnowledgeSpace) -> KnowledgeSpaceView:
    return KnowledgeSpaceView.model_validate(item, from_attributes=True).model_copy(
        update={"text_processing": text_processing_settings(item)}
    )
