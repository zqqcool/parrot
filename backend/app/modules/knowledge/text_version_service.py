from __future__ import annotations

import hashlib

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.clock import utc_now
from app.core.errors import AppError
from app.core.ids import new_id
from app.core.task_dispatch import TaskDispatcher
from app.infrastructure.db.session import DatabaseManager
from app.modules.audit.service import append_audit
from app.modules.iam.schemas import PrincipalContext
from app.modules.knowledge.access import KnowledgeAccessPolicy
from app.modules.knowledge.chunking import split_content
from app.modules.knowledge.document_views import document_view
from app.modules.knowledge.ingestion_repository import KnowledgeIngestionRepository
from app.modules.knowledge.models import KnowledgeChunk, KnowledgeDocumentVersion
from app.modules.knowledge.repository import KnowledgeRepository
from app.modules.knowledge.schemas import (
    KnowledgeDocumentTextVersionCreateRequest,
    KnowledgeDocumentView,
)
from app.modules.knowledge.vector_jobs import enqueue_vector_job
from app.modules.knowledge.view_helpers import process_manual_content, text_processing_settings


class KnowledgeDocumentTextVersionService:
    def __init__(
        self,
        session: AsyncSession,
        database: DatabaseManager,
        dispatcher: TaskDispatcher | None = None,
    ) -> None:
        self.session = session
        self.access = KnowledgeRepository(session)
        self.versions = KnowledgeIngestionRepository(session)
        self.access_policy = KnowledgeAccessPolicy(session, database)
        self.dispatcher = dispatcher

    async def replace(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        document_id: str,
        payload: KnowledgeDocumentTextVersionCreateRequest,
    ) -> KnowledgeDocumentView:
        await self.access_policy.enter(principal, tenant_id, "knowledge.documents.manage")
        document = await self.versions.get_document_for_update(tenant_id, document_id)
        if document is None or document.status != "active":
            raise AppError(
                "RESOURCE_NOT_FOUND", "Knowledge document not found", status.HTTP_404_NOT_FOUND
            )
        space = await self.access_policy.require_space(
            principal, tenant_id, document.space_id, "knowledge.documents.manage", self.access
        )
        if await self.versions.replacement_pending(tenant_id, document.id):
            raise AppError(
                "KNOWLEDGE_VERSION_CONFLICT",
                "A knowledge document replacement is already in progress",
                status.HTTP_409_CONFLICT,
            )
        content = process_manual_content(payload.content, space)
        version = KnowledgeDocumentVersion(
            id=new_id("knowledge_version"),
            tenant_id=tenant_id,
            document_id=document.id,
            version=await self.versions.next_version_number(tenant_id, document.id),
            content_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            created_by_user_id=principal.subject_id,
            chunk_separator=space.chunk_separator,
            chunk_size_chars=space.chunk_size_chars,
            chunk_overlap_chars=space.chunk_overlap_chars,
            normalize_whitespace=space.normalize_whitespace,
            remove_urls_and_emails=space.remove_urls_and_emails,
            content=content,
            status="published",
            extraction_status="completed",
            published_at=utc_now(),
        )
        chunks = split_content(
            content, space.chunk_size_chars, space.chunk_overlap_chars, space.chunk_separator
        )
        previous_version_ids = await self.versions.published_version_ids(tenant_id, document.id)
        await self.versions.supersede_published_versions(tenant_id, document.id)
        document.source_id = None
        self.session.add(version)
        self.session.add_all(
            KnowledgeChunk(
                id=new_id("knowledge_chunk"),
                tenant_id=tenant_id,
                space_id=document.space_id,
                document_version_id=version.id,
                ordinal=ordinal,
                content=chunk,
                citation_anchor=f"chunk-{ordinal}",
                search_vector=func.to_tsvector("simple", chunk),
            )
            for ordinal, chunk in enumerate(chunks, start=1)
        )
        for version_id in previous_version_ids:
            await enqueue_vector_job(
                self.session, tenant_id, version_id, "delete", dispatcher=self.dispatcher
            )
        if space.embedding_config_id is not None:
            await enqueue_vector_job(
                self.session, tenant_id, version.id, "upsert", dispatcher=self.dispatcher
            )
        append_audit(
            self.session,
            principal,
            "knowledge.document.text_version.create",
            "knowledge_document",
            document.id,
            {
                "version": version.version,
                "chunk_count": len(chunks),
                "text_processing": text_processing_settings(space).model_dump(),
            },
            tenant_id=tenant_id,
        )
        return document_view(document, version.version, len(chunks), principal.display_name)
