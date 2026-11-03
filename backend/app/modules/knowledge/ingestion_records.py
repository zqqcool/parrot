from __future__ import annotations

import hashlib

from starlette import status

from app.core.errors import AppError
from app.core.ids import new_id
from app.modules.knowledge.ingestion_repository import KnowledgeIngestionRepository
from app.modules.knowledge.models import (
    KnowledgeDocument,
    KnowledgeDocumentVersion,
    KnowledgeIngestionJob,
    KnowledgeSource,
    KnowledgeSpace,
)
from app.modules.knowledge.title_normalization import normalize_document_title


async def queue_ingestion(
    repository: KnowledgeIngestionRepository,
    source: KnowledgeSource,
    space: KnowledgeSpace,
    content: bytes,
) -> tuple[KnowledgeDocument, KnowledgeDocumentVersion, KnowledgeIngestionJob]:
    if source.target_document_id is None:
        return _new_document_ingestion(source, space, content)
    document = await repository.get_document_for_update(source.tenant_id, source.target_document_id)
    if document is None or document.space_id != source.space_id or document.status != "active":
        raise AppError(
            "RESOURCE_NOT_FOUND", "Knowledge document not found", status.HTTP_404_NOT_FOUND
        )
    if await repository.replacement_pending(source.tenant_id, document.id):
        raise AppError(
            "KNOWLEDGE_VERSION_CONFLICT",
            "A knowledge document replacement is already in progress",
            status.HTTP_409_CONFLICT,
        )
    version_number = await repository.next_version_number(source.tenant_id, document.id)
    version = _version(source, space, content, version_number, document.id)
    job = KnowledgeIngestionJob(
        id=new_id("knowledge_ingestion"),
        tenant_id=source.tenant_id,
        source_id=source.id,
        document_version_id=version.id,
        action="replace",
    )
    return document, version, job


def _new_document_ingestion(
    source: KnowledgeSource, space: KnowledgeSpace, content: bytes
) -> tuple[KnowledgeDocument, KnowledgeDocumentVersion, KnowledgeIngestionJob]:
    document = KnowledgeDocument(
        id=new_id("knowledge_document"),
        tenant_id=source.tenant_id,
        space_id=source.space_id,
        source_id=source.id,
        title=source.title,
        status="processing",
        created_by_user_id=source.created_by_user_id,
        title_key=normalize_document_title(source.title),
    )
    version = _version(source, space, content, 1, document.id)
    job = KnowledgeIngestionJob(
        id=new_id("knowledge_ingestion"),
        tenant_id=source.tenant_id,
        source_id=source.id,
        document_version_id=version.id,
    )
    return document, version, job


def _version(
    source: KnowledgeSource,
    space: KnowledgeSpace,
    content: bytes,
    version_number: int,
    document_id: str,
) -> KnowledgeDocumentVersion:
    return KnowledgeDocumentVersion(
        id=new_id("knowledge_version"),
        tenant_id=source.tenant_id,
        document_id=document_id,
        source_id=source.id,
        version=version_number,
        content_sha256=hashlib.sha256(content).hexdigest(),
        created_by_user_id=source.created_by_user_id,
        status="processing",
        extraction_status="pending",
        chunk_separator=getattr(space, "chunk_separator", r"\n\n"),
        chunk_size_chars=space.chunk_size_chars,
        chunk_overlap_chars=space.chunk_overlap_chars,
        normalize_whitespace=bool(getattr(space, "normalize_whitespace", False)),
        remove_urls_and_emails=bool(getattr(space, "remove_urls_and_emails", False)),
        content="",
    )
