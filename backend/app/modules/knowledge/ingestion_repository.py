from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.knowledge.models import (
    KnowledgeDocument,
    KnowledgeDocumentVersion,
    KnowledgeIngestionJob,
    KnowledgeSource,
)


class KnowledgeIngestionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_source(self, tenant_id: str, source_id: str) -> KnowledgeSource | None:
        return await self.session.scalar(
            select(KnowledgeSource).where(
                KnowledgeSource.tenant_id == tenant_id, KnowledgeSource.id == source_id
            )
        )

    async def get_source_for_update(self, tenant_id: str, source_id: str) -> KnowledgeSource | None:
        return await self.session.scalar(
            select(KnowledgeSource)
            .where(KnowledgeSource.tenant_id == tenant_id, KnowledgeSource.id == source_id)
            .with_for_update()
        )

    async def delete_source(self, source: KnowledgeSource) -> None:
        await self.session.delete(source)

    async def get_job(
        self, tenant_id: str, job_id: str
    ) -> tuple[KnowledgeIngestionJob, KnowledgeDocumentVersion, KnowledgeDocument] | None:
        row = await self.session.execute(
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
            .where(KnowledgeIngestionJob.tenant_id == tenant_id, KnowledgeIngestionJob.id == job_id)
        )
        return row.tuples().one_or_none()

    async def get_job_by_source(
        self, tenant_id: str, source_id: str
    ) -> tuple[KnowledgeIngestionJob, KnowledgeDocumentVersion, KnowledgeDocument] | None:
        row = await self.session.execute(
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
                KnowledgeIngestionJob.tenant_id == tenant_id,
                KnowledgeIngestionJob.source_id == source_id,
            )
        )
        return row.tuples().one_or_none()

    async def list_active_jobs(
        self, tenant_id: str, space_id: str
    ) -> tuple[tuple[KnowledgeIngestionJob, KnowledgeDocumentVersion, KnowledgeDocument], ...]:
        rows = await self.session.execute(
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
                KnowledgeIngestionJob.tenant_id == tenant_id,
                KnowledgeDocument.space_id == space_id,
                KnowledgeIngestionJob.status.in_(("queued", "running")),
            )
            .order_by(KnowledgeIngestionJob.created_at, KnowledgeIngestionJob.id)
        )
        return tuple(rows.tuples())

    async def get_document(self, tenant_id: str, document_id: str) -> KnowledgeDocument | None:
        return await self.session.scalar(
            select(KnowledgeDocument).where(
                KnowledgeDocument.tenant_id == tenant_id, KnowledgeDocument.id == document_id
            )
        )

    async def get_document_for_update(
        self, tenant_id: str, document_id: str
    ) -> KnowledgeDocument | None:
        return await self.session.scalar(
            select(KnowledgeDocument)
            .where(
                KnowledgeDocument.tenant_id == tenant_id,
                KnowledgeDocument.id == document_id,
            )
            .with_for_update()
        )

    async def next_version_number(self, tenant_id: str, document_id: str) -> int:
        current = await self.session.scalar(
            select(func.max(KnowledgeDocumentVersion.version)).where(
                KnowledgeDocumentVersion.tenant_id == tenant_id,
                KnowledgeDocumentVersion.document_id == document_id,
            )
        )
        return int(current or 0) + 1

    async def replacement_pending(self, tenant_id: str, document_id: str) -> bool:
        value = await self.session.scalar(
            select(KnowledgeDocumentVersion.id).where(
                KnowledgeDocumentVersion.tenant_id == tenant_id,
                KnowledgeDocumentVersion.document_id == document_id,
                KnowledgeDocumentVersion.status == "processing",
            )
        )
        return value is not None

    async def published_version_ids(self, tenant_id: str, document_id: str) -> tuple[str, ...]:
        rows = await self.session.scalars(
            select(KnowledgeDocumentVersion.id).where(
                KnowledgeDocumentVersion.tenant_id == tenant_id,
                KnowledgeDocumentVersion.document_id == document_id,
                KnowledgeDocumentVersion.status == "published",
            )
        )
        return tuple(rows)

    async def supersede_published_versions(self, tenant_id: str, document_id: str) -> None:
        await self.session.execute(
            update(KnowledgeDocumentVersion)
            .where(
                KnowledgeDocumentVersion.tenant_id == tenant_id,
                KnowledgeDocumentVersion.document_id == document_id,
                KnowledgeDocumentVersion.status == "published",
            )
            .values(status="superseded")
        )
