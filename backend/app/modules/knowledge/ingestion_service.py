from __future__ import annotations

import hashlib
import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.errors import AppError
from app.core.ids import new_id
from app.core.object_storage import ObjectStoragePort, ObjectUploadGrant
from app.core.task_dispatch import TaskDispatcher
from app.infrastructure.db.session import DatabaseManager
from app.modules.audit.service import append_audit
from app.modules.iam.schemas import PrincipalContext
from app.modules.knowledge.access import KnowledgeAccessPolicy
from app.modules.knowledge.ingestion_object_promotion import (
    KnowledgeStagingObjectGoneError,
    promote_staged_object,
)
from app.modules.knowledge.ingestion_records import queue_ingestion
from app.modules.knowledge.ingestion_repository import KnowledgeIngestionRepository
from app.modules.knowledge.ingestion_validation import (
    validate_declared_file,
    validate_uploaded_file,
)
from app.modules.knowledge.ingestion_views import ingestion_view as _ingestion_view
from app.modules.knowledge.models import KnowledgeSource, KnowledgeSpace
from app.modules.knowledge.repository import KnowledgeRepository
from app.modules.knowledge.schemas import (
    KnowledgeDocumentVersionUploadRequest,
    KnowledgeIngestionView,
    KnowledgeSourceConfirmRequest,
    KnowledgeSourceUploadRequest,
)
from app.modules.knowledge.title_normalization import (
    available_title_error,
    is_available_title_conflict,
    normalize_document_title,
)

logger = logging.getLogger(__name__)


class KnowledgeIngestionService:
    def __init__(
        self,
        session: AsyncSession,
        database: DatabaseManager,
        object_storage: ObjectStoragePort,
        max_upload_bytes: int,
        dispatcher: TaskDispatcher | None = None,
    ) -> None:
        self.session = session
        self.database = database
        self.storage = object_storage
        self.max_upload_bytes = max_upload_bytes
        self.dispatcher = dispatcher
        self.access = KnowledgeRepository(session)
        self.repository = KnowledgeIngestionRepository(session)
        self.access_policy = KnowledgeAccessPolicy(session, database)

    async def issue_upload(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        space_id: str,
        payload: KnowledgeSourceUploadRequest,
    ) -> tuple[KnowledgeSource, ObjectUploadGrant]:
        await self._space(principal, tenant_id, space_id, "knowledge.documents.manage")
        title = payload.title.strip()
        await self._ensure_available_title(tenant_id, space_id, normalize_document_title(title))
        return await self._issue_upload(principal, tenant_id, space_id, payload, title, None)

    async def issue_replacement_upload(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        document_id: str,
        payload: KnowledgeDocumentVersionUploadRequest,
    ) -> tuple[KnowledgeSource, ObjectUploadGrant]:
        await self._enter(principal, tenant_id, "knowledge.documents.manage")
        document = await self.repository.get_document(tenant_id, document_id)
        if document is None or document.status != "active":
            raise AppError(
                "RESOURCE_NOT_FOUND", "Knowledge document not found", status.HTTP_404_NOT_FOUND
            )
        await self._space(principal, tenant_id, document.space_id, "knowledge.documents.manage")
        return await self._issue_upload(
            principal, tenant_id, document.space_id, payload, document.title, document.id
        )

    async def _issue_upload(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        space_id: str,
        payload: KnowledgeSourceUploadRequest | KnowledgeDocumentVersionUploadRequest,
        title: str,
        target_document_id: str | None,
    ) -> tuple[KnowledgeSource, ObjectUploadGrant]:
        file = validate_declared_file(
            payload.content_type, payload.filename, payload.size_bytes, self.max_upload_bytes
        )
        source = KnowledgeSource(
            id=new_id("knowledge_source"),
            tenant_id=tenant_id,
            space_id=space_id,
            source_kind="upload",
            title=title,
            original_filename=payload.filename,
            content_type=file.content_type,
            declared_size_bytes=payload.size_bytes,
            target_document_id=target_document_id,
            created_by_user_id=principal.subject_id,
        )
        staging_key = f"staging/knowledge/{tenant_id}/{space_id}/{source.id}/upload{file.extension}"
        source.staging_key = staging_key
        self.session.add(source)
        await self.session.flush()
        append_audit(
            self.session,
            principal,
            "knowledge.source.upload_grant.issue",
            "knowledge_source",
            source.id,
            {
                "space_id": space_id,
                "content_type": file.content_type,
                "size_bytes": payload.size_bytes,
                "target_document_id": target_document_id,
            },
            tenant_id=tenant_id,
        )
        return source, await self.storage.issue_upload_grant(
            staging_key, file.content_type, payload.size_bytes
        )

    async def confirm_upload(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        source_id: str,
        payload: KnowledgeSourceConfirmRequest,
    ) -> KnowledgeIngestionView:
        source = await self._source(
            principal, tenant_id, source_id, "knowledge.documents.manage", for_update=True
        )
        if source.status != "staging":
            return await self._confirmed_upload(tenant_id, source)
        if payload.staging_key != source.staging_key:
            raise AppError(
                "KNOWLEDGE_UPLOAD_INVALID",
                "Knowledge upload cannot be confirmed",
                status.HTTP_422_UNPROCESSABLE_CONTENT,
            )
        return await self._confirm_staged_source(principal, tenant_id, source, payload.staging_key)

    async def retry_upload_confirmation(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        source_id: str,
    ) -> KnowledgeIngestionView:
        source = await self._source(
            principal, tenant_id, source_id, "knowledge.documents.manage", for_update=True
        )
        if source.status != "staging":
            return await self._confirmed_upload(tenant_id, source)
        if source.staging_key is None:
            raise AppError(
                "KNOWLEDGE_UPLOAD_INVALID",
                "Knowledge upload cannot be confirmed",
                status.HTTP_422_UNPROCESSABLE_CONTENT,
            )
        return await self._confirm_staged_source(principal, tenant_id, source, source.staging_key)

    async def cleanup_staging_source(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        source_id: str,
    ) -> None:
        source = await self._source(
            principal, tenant_id, source_id, "knowledge.documents.manage", for_update=True
        )
        if source.status != "staging" or source.staging_key is None:
            raise AppError(
                "KNOWLEDGE_SOURCE_STATE_INVALID",
                "Knowledge upload state has changed",
                status.HTTP_409_CONFLICT,
            )
        await self._purge_staging_source(
            principal,
            tenant_id,
            source,
            audit_action="knowledge.source.staging.cleanup",
        )

    async def _confirm_staged_source(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        source: KnowledgeSource,
        staging_key: str,
    ) -> KnowledgeIngestionView:
        if source.status != "staging":
            return await self._confirmed_upload(tenant_id, source)
        staged = await self.storage.read(staging_key)
        if staged is None:
            await self._abandon_unrecoverable_staging(principal, tenant_id, source)
            raise AppError(
                "KNOWLEDGE_UPLOAD_NOT_FOUND",
                "Knowledge upload was not found",
                status.HTTP_404_NOT_FOUND,
            )
        file = validate_uploaded_file(
            staged.content, source.content_type, source.original_filename, self.max_upload_bytes
        )
        canonical_key = (
            f"knowledge/{tenant_id}/{source.space_id}/{source.id}/source{file.extension}"
        )
        try:
            await promote_staged_object(self.storage, staging_key, canonical_key, staged)
        except KnowledgeStagingObjectGoneError as exc:
            await self._abandon_unrecoverable_staging(principal, tenant_id, source)
            raise AppError(
                "KNOWLEDGE_UPLOAD_NOT_FOUND",
                "Knowledge upload was not found",
                status.HTTP_404_NOT_FOUND,
            ) from exc
        try:
            space = await self._space(
                principal, tenant_id, source.space_id, "knowledge.documents.manage"
            )
            document, version, job = await queue_ingestion(
                self.repository, source, space, staged.content
            )
            source.content_sha256 = hashlib.sha256(staged.content).hexdigest()
            source.object_key = canonical_key
            source.staging_key = None
            source.status = "queued"
            self.session.add_all((document, version, job))
            try:
                await self.session.flush()
            except IntegrityError as exc:
                if is_available_title_conflict(exc):
                    raise available_title_error() from exc
                raise
            append_audit(
                self.session,
                principal,
                "knowledge.source.upload.confirm",
                "knowledge_source",
                source.id,
                {
                    "document_id": document.id,
                    "version_id": version.id,
                    "size_bytes": len(staged.content),
                },
                tenant_id=tenant_id,
            )
            await self.session.commit()
        except Exception:
            await self._delete_canonical(canonical_key)
            raise
        await self._dispatch_ingestion(tenant_id, job.id)
        return _ingestion_view(job, document)

    async def get_job(
        self, principal: PrincipalContext, tenant_id: str, job_id: str
    ) -> KnowledgeIngestionView:
        row = await self.repository.get_job(tenant_id, job_id)
        if row is None:
            raise AppError(
                "RESOURCE_NOT_FOUND", "Knowledge ingestion was not found", status.HTTP_404_NOT_FOUND
            )
        job, _version, document = row
        await self._space(principal, tenant_id, document.space_id, "knowledge.documents.read")
        return _ingestion_view(job, document)

    async def list_active_jobs(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        space_id: str,
    ) -> tuple[KnowledgeIngestionView, ...]:
        await self._space(principal, tenant_id, space_id, "knowledge.documents.read")
        rows = await self.repository.list_active_jobs(tenant_id, space_id)
        return tuple(_ingestion_view(job, document) for job, _version, document in rows)

    async def _source(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        source_id: str,
        permission: str,
        *,
        for_update: bool = False,
    ) -> KnowledgeSource:
        await self._enter(principal, tenant_id, permission)
        get_source = (
            self.repository.get_source_for_update if for_update else self.repository.get_source
        )
        source = await get_source(tenant_id, source_id)
        if source is None:
            raise AppError(
                "RESOURCE_NOT_FOUND", "Knowledge source not found", status.HTTP_404_NOT_FOUND
            )
        await self._space(principal, tenant_id, source.space_id, permission)
        return source

    async def _confirmed_upload(
        self, tenant_id: str, source: KnowledgeSource
    ) -> KnowledgeIngestionView:
        row = await self.repository.get_job_by_source(tenant_id, source.id)
        if row is None:
            raise AppError(
                "KNOWLEDGE_UPLOAD_INVALID",
                "Knowledge upload cannot be confirmed",
                status.HTTP_422_UNPROCESSABLE_CONTENT,
            )
        job, _version, document = row
        await self.session.commit()
        if job.status == "queued":
            await self._dispatch_ingestion(tenant_id, job.id)
        return _ingestion_view(job, document)

    async def _dispatch_ingestion(self, tenant_id: str, job_id: str) -> None:
        if self.dispatcher is None:
            return
        try:
            await self.dispatcher.dispatch_knowledge_ingestion(tenant_id, job_id)
        except Exception as exc:
            logger.exception(
                "Unable to dispatch committed knowledge ingestion",
                extra={"tenant_id": tenant_id, "job_id": job_id},
            )
            raise AppError(
                "DEPENDENCY_UNAVAILABLE",
                "Knowledge ingestion queue is unavailable",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            ) from exc

    async def _space(
        self, principal: PrincipalContext, tenant_id: str, space_id: str, permission: str
    ) -> KnowledgeSpace:
        return await self.access_policy.require_space(
            principal, tenant_id, space_id, permission, self.access
        )

    async def _enter(self, principal: PrincipalContext, tenant_id: str, permission: str) -> None:
        await self.access_policy.enter(principal, tenant_id, permission)

    async def _delete_canonical(self, key: str) -> None:
        try:
            await self.storage.delete(key)
        except Exception:
            logger.exception(
                "Unable to remove unlinked knowledge object", extra={"object_key": key}
            )

    async def _abandon_unrecoverable_staging(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        source: KnowledgeSource,
    ) -> None:
        await self._purge_staging_source(
            principal,
            tenant_id,
            source,
            audit_action="knowledge.source.staging.abandon",
            audit_payload={"reason": "unrecoverable_object"},
        )

    async def _purge_staging_source(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        source: KnowledgeSource,
        *,
        audit_action: str,
        audit_payload: dict[str, object] | None = None,
    ) -> None:
        source_id = source.id
        space_id = source.space_id
        staging_key = source.staging_key
        if staging_key is not None:
            try:
                await self.storage.delete(staging_key)
            except Exception:
                logger.warning(
                    "Unable to delete knowledge staging object during purge",
                    extra={"tenant_id": tenant_id, "source_id": source_id},
                    exc_info=True,
                )
        await self.repository.delete_source(source)
        append_audit(
            self.session,
            principal,
            audit_action,
            "knowledge_source",
            source_id,
            {"space_id": space_id, **(audit_payload or {})},
            tenant_id=tenant_id,
        )
        await self.session.commit()

    async def _ensure_available_title(self, tenant_id: str, space_id: str, title_key: str) -> None:
        if await self.access.available_document_exists(tenant_id, space_id, title_key):
            raise available_title_error()
