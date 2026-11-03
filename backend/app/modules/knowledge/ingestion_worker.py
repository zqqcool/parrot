from __future__ import annotations

import asyncio
import logging
import os
import socket
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import SYSTEM_CLOCK, Clock
from app.core.config import AppConfig
from app.core.object_storage import ObjectStoragePort
from app.core.task_dispatch import TaskDispatcher
from app.infrastructure.db.session import DatabaseManager
from app.modules.knowledge.extraction import default_knowledge_extractor
from app.modules.knowledge.extraction.types import ExtractedDocument
from app.modules.knowledge.extractor import KnowledgeExtractionError
from app.modules.knowledge.ingestion_publish import prepare_slide_media, publish_extracted_document
from app.modules.knowledge.models import (
    KnowledgeDocument,
    KnowledgeDocumentVersion,
    KnowledgeIngestionJob,
    KnowledgeSource,
)
from app.modules.knowledge.preprocessing import KnowledgeTextProcessingError

logger = logging.getLogger(__name__)
_INGESTION_LEASE_DURATION = timedelta(minutes=10)


@dataclass(frozen=True)
class ClaimedKnowledgeIngestion:
    id: str
    tenant_id: str
    source_id: str
    document_version_id: str


class KnowledgeIngestionWorker:
    """TaskIQ-invoked tenant-scoped document extractor."""

    def __init__(
        self,
        settings: AppConfig,
        object_storage: ObjectStoragePort,
        *,
        dispatcher: TaskDispatcher | None = None,
        clock: Clock = SYSTEM_CLOCK,
    ) -> None:
        self._settings = settings
        self._storage = object_storage
        self._database = DatabaseManager(settings.database)
        self._clock = clock
        self._dispatcher = dispatcher
        self._owner = f"{socket.gethostname()}:{os.getpid()}:taskiq-knowledge-ingest"

    async def close(self) -> None:
        await self._database.dispose()

    async def process(self, tenant_id: str, job_id: str) -> bool:
        claim = await self._claim(tenant_id, job_id)
        if claim is None:
            return False
        await self._process(claim)
        return True

    async def _claim(self, tenant_id: str, job_id: str) -> ClaimedKnowledgeIngestion | None:
        now = self._clock.now()
        async with self._database.session() as session:
            await self._database.set_tenant(session, tenant_id)
            job = await session.scalar(
                select(KnowledgeIngestionJob)
                .where(
                    KnowledgeIngestionJob.tenant_id == tenant_id,
                    KnowledgeIngestionJob.id == job_id,
                    KnowledgeIngestionJob.status.in_(("queued", "running")),
                    or_(
                        KnowledgeIngestionJob.lease_until.is_(None),
                        KnowledgeIngestionJob.lease_until < now,
                    ),
                )
                .order_by(KnowledgeIngestionJob.created_at)
                .with_for_update(skip_locked=True)
            )
            if job is None:
                return None
            job.status = "running"
            job.attempts += 1
            job.lease_owner = self._owner
            job.lease_until = now + _INGESTION_LEASE_DURATION
            return ClaimedKnowledgeIngestion(
                job.id, tenant_id, job.source_id, job.document_version_id
            )

    async def _process(self, claim: ClaimedKnowledgeIngestion) -> None:
        logger.info(
            "Knowledge ingestion job started",
            extra={"tenant_id": claim.tenant_id, "source_id": claim.source_id, "job_id": claim.id},
        )
        try:
            source = await self._source(claim)
            if source is None or source.object_key is None:
                raise KnowledgeExtractionError("KNOWLEDGE_SOURCE_UNAVAILABLE")
            stored = await self._storage.read(source.object_key)
            if stored is None:
                raise KnowledgeExtractionError("KNOWLEDGE_SOURCE_UNAVAILABLE")
            extracted = await asyncio.to_thread(
                default_knowledge_extractor().extract,
                stored.content,
                source.content_type,
                max_chars=self._settings.knowledge.max_extracted_chars,
                max_pdf_pages=self._settings.knowledge.max_pdf_pages,
                max_slides=self._settings.knowledge.max_pptx_slides,
                max_embedded_images=self._settings.knowledge.max_embedded_images_for(
                    source.content_type
                ),
                max_sheets=self._settings.knowledge.max_xlsx_sheets,
                max_rows_per_region=self._settings.knowledge.max_xlsx_rows_per_region,
            )
            if self._settings.knowledge.slide_render_enabled:
                extracted = await asyncio.to_thread(prepare_slide_media, extracted, stored.content)
            await self._publish(claim, extracted)
            logger.info(
                "Knowledge ingestion job completed",
                extra={
                    "tenant_id": claim.tenant_id,
                    "source_id": claim.source_id,
                    "job_id": claim.id,
                },
            )
        except KnowledgeTextProcessingError as error:
            await self._fail(claim, str(error))
        except KnowledgeExtractionError as error:
            await self._fail(claim, str(error))
        except Exception:
            logger.exception(
                "Knowledge ingestion failed",
                extra={
                    "tenant_id": claim.tenant_id,
                    "source_id": claim.source_id,
                    "job_id": claim.id,
                },
            )
            await self._fail(claim, "KNOWLEDGE_INGESTION_FAILED")

    async def _source(self, claim: ClaimedKnowledgeIngestion) -> KnowledgeSource | None:
        async with self._database.session() as session:
            await self._database.set_tenant(session, claim.tenant_id)
            return await session.scalar(
                select(KnowledgeSource).where(
                    KnowledgeSource.tenant_id == claim.tenant_id,
                    KnowledgeSource.id == claim.source_id,
                    KnowledgeSource.status.in_(("queued", "processing")),
                )
            )

    async def _publish(
        self,
        claim: ClaimedKnowledgeIngestion,
        extracted: ExtractedDocument,
    ) -> None:
        async with self._database.session() as session:
            await self._database.set_tenant(session, claim.tenant_id)
            state = await self._state(session, claim)
            if state is None:
                return
            job, version, document = state
            await publish_extracted_document(
                session,
                tenant_id=claim.tenant_id,
                source_id=claim.source_id,
                job=job,
                version=version,
                document=document,
                extracted=extracted,
                clock=self._clock,
                dispatcher=self._dispatcher,
                object_storage=self._storage,
            )

    async def _fail(self, claim: ClaimedKnowledgeIngestion, code: str) -> None:
        async with self._database.session() as session:
            await self._database.set_tenant(session, claim.tenant_id)
            state = await self._state(session, claim)
            if state is None:
                return
            job, version, document = state
            source = await session.scalar(
                select(KnowledgeSource).where(
                    KnowledgeSource.tenant_id == claim.tenant_id,
                    KnowledgeSource.id == claim.source_id,
                )
            )
            if source is not None:
                source.status = "failed"
            if job.action != "replace":
                document.status = "failed"
            version.status = "failed"
            version.extraction_status = "failed"
            job.status = "failed"
            job.error_code = code
            job.lease_owner = None
            job.lease_until = None

    async def _state(
        self, session: AsyncSession, claim: ClaimedKnowledgeIngestion
    ) -> tuple[KnowledgeIngestionJob, KnowledgeDocumentVersion, KnowledgeDocument] | None:
        result = await session.execute(
            select(KnowledgeIngestionJob, KnowledgeDocumentVersion, KnowledgeDocument)
            .join(
                KnowledgeDocumentVersion,
                (KnowledgeDocumentVersion.tenant_id == KnowledgeIngestionJob.tenant_id)
                & (KnowledgeDocumentVersion.id == KnowledgeIngestionJob.document_version_id),
            )
            .join(
                KnowledgeDocument,
                (KnowledgeDocument.tenant_id == KnowledgeDocumentVersion.tenant_id)
                & (KnowledgeDocument.id == KnowledgeDocumentVersion.document_id),
            )
            .where(
                KnowledgeIngestionJob.tenant_id == claim.tenant_id,
                KnowledgeIngestionJob.id == claim.id,
                KnowledgeIngestionJob.lease_owner == self._owner,
            )
        )
        return result.tuples().one_or_none()
