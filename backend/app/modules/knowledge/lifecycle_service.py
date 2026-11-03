from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePath

from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.errors import AppError
from app.core.object_storage import ObjectStoragePort
from app.core.task_dispatch import TaskDispatcher
from app.infrastructure.db.session import DatabaseManager
from app.modules.audit.service import append_audit
from app.modules.iam.schemas import PrincipalContext
from app.modules.knowledge.access import KnowledgeAccessPolicy
from app.modules.knowledge.ingestion_repository import KnowledgeIngestionRepository
from app.modules.knowledge.media_repository import KnowledgeMediaRepository
from app.modules.knowledge.media_types import media_file_extension
from app.modules.knowledge.models import KnowledgeChunk, KnowledgeDocument, KnowledgeDocumentVersion
from app.modules.knowledge.repository import KnowledgeRepository
from app.modules.knowledge.schemas import (
    KnowledgeDocumentChunkPageView,
    KnowledgeDocumentChunkView,
    KnowledgeDocumentVersionView,
    KnowledgeTextProcessingSettings,
)
from app.modules.knowledge.vector_jobs import enqueue_vector_job


@dataclass(frozen=True)
class KnowledgeSourceFile:
    filename: str
    content_type: str
    content: bytes


@dataclass(frozen=True)
class KnowledgeMediaFile:
    filename: str
    content_type: str
    content: bytes


class KnowledgeDocumentLifecycleService:
    def __init__(
        self,
        session: AsyncSession,
        database: DatabaseManager,
        object_storage: ObjectStoragePort | None = None,
        dispatcher: TaskDispatcher | None = None,
    ) -> None:
        self.session = session
        self.database = database
        self.storage = object_storage
        self.dispatcher = dispatcher
        self.repository = KnowledgeRepository(session)
        self.media = KnowledgeMediaRepository(session)
        self.ingestions = KnowledgeIngestionRepository(session)
        self.access_policy = KnowledgeAccessPolicy(session, database)

    async def list_versions(
        self, principal: PrincipalContext, tenant_id: str, document_id: str
    ) -> tuple[KnowledgeDocumentVersionView, ...]:
        _document, versions = await self._document(
            principal, tenant_id, document_id, "knowledge.documents.read"
        )
        return tuple(_version_view(item) for item in versions)

    async def list_chunks(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        document_id: str,
        version_id: str,
        *,
        page: int,
        page_size: int,
    ) -> KnowledgeDocumentChunkPageView:
        _document, versions = await self._document(
            principal, tenant_id, document_id, "knowledge.documents.read"
        )
        version = next((item for item in versions if item.id == version_id), None)
        if version is None or version.status not in {"published", "superseded"}:
            raise AppError(
                "RESOURCE_NOT_FOUND",
                "Knowledge document version not found",
                status.HTTP_404_NOT_FOUND,
            )
        chunks, total = await self.repository.document_chunks(
            tenant_id, version.id, page=page, page_size=page_size
        )
        return KnowledgeDocumentChunkPageView(
            items=tuple(_chunk_view(item) for item in chunks),
            page=page,
            page_size=page_size,
            total=total,
        )

    async def archive(self, principal: PrincipalContext, tenant_id: str, document_id: str) -> None:
        document, versions = await self._document(
            principal, tenant_id, document_id, "knowledge.documents.manage"
        )
        if document.status == "archived":
            return
        document.status = "archived"
        for version in versions:
            if version.status in {"published", "superseded"}:
                await enqueue_vector_job(
                    self.session, tenant_id, version.id, "delete", dispatcher=self.dispatcher
                )
        await self.session.flush()
        append_audit(
            self.session,
            principal,
            "knowledge.document.archive",
            "knowledge_document",
            document.id,
            {"space_id": document.space_id},
            tenant_id=tenant_id,
        )

    async def source_file(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        document_id: str,
        version_id: str,
    ) -> KnowledgeSourceFile:
        document, versions = await self._document(
            principal, tenant_id, document_id, "knowledge.documents.read"
        )
        version = next((item for item in versions if item.id == version_id), None)
        if version is None or version.status not in {"published", "superseded"}:
            raise AppError(
                "RESOURCE_NOT_FOUND", "Knowledge source not found", status.HTTP_404_NOT_FOUND
            )
        result = await self._read_source(tenant_id, document, version)
        append_audit(
            self.session,
            principal,
            "knowledge.source.download",
            "knowledge_document_version",
            version.id,
            {"document_id": document.id, "space_id": document.space_id},
            tenant_id=tenant_id,
        )
        return result

    async def _read_source(
        self,
        tenant_id: str,
        document: KnowledgeDocument,
        version: KnowledgeDocumentVersion,
    ) -> KnowledgeSourceFile:
        if version.source_id is None:
            return KnowledgeSourceFile(
                filename=_safe_filename(f"{document.title}-v{version.version}.txt"),
                content_type="text/plain; charset=utf-8",
                content=version.content.encode("utf-8"),
            )
        source = await self.ingestions.get_source(tenant_id, version.source_id)
        if source is None or source.object_key is None or self.storage is None:
            raise AppError(
                "KNOWLEDGE_SOURCE_UNAVAILABLE",
                "Knowledge source is temporarily unavailable",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        stored = await self.storage.read(source.object_key)
        if stored is None:
            raise AppError(
                "KNOWLEDGE_SOURCE_UNAVAILABLE",
                "Knowledge source is temporarily unavailable",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return KnowledgeSourceFile(
            filename=_safe_filename(source.original_filename),
            content_type=source.content_type,
            content=stored.content,
        )

    async def media_file(
        self, principal: PrincipalContext, tenant_id: str, asset_id: str
    ) -> KnowledgeMediaFile:
        await self._enter(principal, tenant_id, "knowledge.documents.read")
        asset = await self.media.downloadable(tenant_id, asset_id)
        if asset is None:
            raise AppError(
                "RESOURCE_NOT_FOUND", "Knowledge media asset not found", status.HTTP_404_NOT_FOUND
            )
        await self.access_policy.active_space(
            principal,
            tenant_id,
            asset.space_id,
            self.repository,
            not_found_message="Knowledge media asset not found",
        )
        if self.storage is None:
            raise AppError(
                "KNOWLEDGE_SOURCE_UNAVAILABLE",
                "Knowledge source is temporarily unavailable",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        stored = await self.storage.read(asset.object_key)
        if stored is None:
            raise AppError(
                "RESOURCE_NOT_FOUND", "Knowledge media asset not found", status.HTTP_404_NOT_FOUND
            )
        append_audit(
            self.session,
            principal,
            "knowledge.media.download",
            "knowledge_media_asset",
            asset.id,
            {"space_id": asset.space_id, "slide_no": asset.slide_no},
            tenant_id=tenant_id,
        )
        extension = media_file_extension(asset.content_type)
        return KnowledgeMediaFile(
            filename=_safe_filename(f"{asset.asset_kind}-{asset.slide_no or 0}{extension}"),
            content_type=asset.content_type,
            content=stored.content,
        )

    async def _document(
        self, principal: PrincipalContext, tenant_id: str, document_id: str, permission: str
    ) -> tuple[KnowledgeDocument, tuple[KnowledgeDocumentVersion, ...]]:
        await self._enter(principal, tenant_id, permission)
        row = await self.repository.document_versions(tenant_id, document_id)
        if row is None:
            raise AppError(
                "RESOURCE_NOT_FOUND", "Knowledge document not found", status.HTTP_404_NOT_FOUND
            )
        document, versions = row
        await self.access_policy.active_space(
            principal,
            tenant_id,
            document.space_id,
            self.repository,
            not_found_message="Knowledge document not found",
        )
        return document, versions

    async def _enter(self, principal: PrincipalContext, tenant_id: str, permission: str) -> None:
        await self.access_policy.enter(
            principal,
            tenant_id,
            permission,
            not_found_message="Knowledge document not found",
        )


def _version_view(item: KnowledgeDocumentVersion) -> KnowledgeDocumentVersionView:
    return KnowledgeDocumentVersionView.model_validate(item, from_attributes=True).model_copy(
        update={
            "text_processing": KnowledgeTextProcessingSettings(
                normalize_whitespace=bool(getattr(item, "normalize_whitespace", False)),
                remove_urls_and_emails=bool(getattr(item, "remove_urls_and_emails", False)),
            )
        }
    )


def _chunk_view(item: KnowledgeChunk) -> KnowledgeDocumentChunkView:
    return KnowledgeDocumentChunkView(
        id=item.id,
        ordinal=item.ordinal,
        citation_anchor=item.citation_anchor,
        content=item.content,
        content_chars=len(item.content),
    )


def _safe_filename(value: str) -> str:
    basename = PurePath(value.replace("\\", "/")).name
    safe = "".join(character for character in basename if character >= " " and character != "\x7f")
    return safe[:300] or "knowledge-source"
