from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.iam.models import User
from app.modules.knowledge.models import (
    KnowledgeDocumentVersion,
    KnowledgeIngestionJob,
    KnowledgeSource,
)


@dataclass(frozen=True)
class KnowledgeSourceActivityRecord:
    source: KnowledgeSource
    document_id: str | None
    attempts: int
    error_code: str | None
    created_by_user_id: str
    created_by_display_name: str


class KnowledgeSourceActivityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_for_space(
        self,
        tenant_id: str,
        space_id: str,
        *,
        page: int,
        page_size: int,
    ) -> tuple[tuple[KnowledgeSourceActivityRecord, ...], int]:
        total = await self.session.scalar(
            select(func.count())
            .select_from(KnowledgeSource)
            .where(
                KnowledgeSource.tenant_id == tenant_id,
                KnowledgeSource.space_id == space_id,
            )
        )
        rows = await self.session.execute(
            select(
                KnowledgeSource,
                func.coalesce(
                    KnowledgeDocumentVersion.document_id,
                    KnowledgeSource.target_document_id,
                ),
                KnowledgeIngestionJob.attempts,
                KnowledgeIngestionJob.error_code,
                User.id,
                User.display_name,
            )
            .outerjoin(
                KnowledgeIngestionJob,
                (KnowledgeIngestionJob.tenant_id == KnowledgeSource.tenant_id)
                & (KnowledgeIngestionJob.source_id == KnowledgeSource.id),
            )
            .outerjoin(
                KnowledgeDocumentVersion,
                (KnowledgeDocumentVersion.tenant_id == KnowledgeIngestionJob.tenant_id)
                & (KnowledgeDocumentVersion.id == KnowledgeIngestionJob.document_version_id),
            )
            .join(User, User.id == KnowledgeSource.created_by_user_id)
            .where(
                KnowledgeSource.tenant_id == tenant_id,
                KnowledgeSource.space_id == space_id,
            )
            .order_by(KnowledgeSource.created_at.desc(), KnowledgeSource.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        records = tuple(
            KnowledgeSourceActivityRecord(
                source=source,
                document_id=document_id,
                attempts=int(attempts or 0),
                error_code=error_code,
                created_by_user_id=created_by_user_id,
                created_by_display_name=created_by_display_name,
            )
            for (
                source,
                document_id,
                attempts,
                error_code,
                created_by_user_id,
                created_by_display_name,
            ) in rows.tuples()
        )
        return records, int(total or 0)
