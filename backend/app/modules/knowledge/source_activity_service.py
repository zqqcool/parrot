from __future__ import annotations

from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.session import DatabaseManager
from app.modules.iam.schemas import PrincipalContext, UserReference
from app.modules.iam.user_references import UserReferenceResolver
from app.modules.knowledge.access import KnowledgeAccessPolicy
from app.modules.knowledge.repository import KnowledgeRepository
from app.modules.knowledge.schemas import (
    KnowledgeSourceActivityPageView,
    KnowledgeSourceActivityView,
)
from app.modules.knowledge.source_activity_repository import (
    KnowledgeSourceActivityRecord,
    KnowledgeSourceActivityRepository,
)


class KnowledgeSourceActivityService:
    def __init__(
        self, session: AsyncSession, database: DatabaseManager, staging_retention_hours: int = 24
    ) -> None:
        self.access_policy = KnowledgeAccessPolicy(session, database)
        self.spaces = KnowledgeRepository(session)
        self.repository = KnowledgeSourceActivityRepository(session)
        self.user_references = UserReferenceResolver(session)
        self.staging_retention_hours = staging_retention_hours

    async def list_for_space(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        space_id: str,
        *,
        page: int,
        page_size: int,
    ) -> KnowledgeSourceActivityPageView:
        await self.access_policy.require_space(
            principal,
            tenant_id,
            space_id,
            "knowledge.documents.read",
            self.spaces,
        )
        records, total = await self.repository.list_for_space(
            tenant_id,
            space_id,
            page=page,
            page_size=page_size,
        )
        users = await self.user_references.resolve(
            tenant_id, (record.created_by_user_id for record in records)
        )
        return KnowledgeSourceActivityPageView(
            items=tuple(
                _activity_view(
                    record,
                    users.get(record.created_by_user_id),
                    self.staging_retention_hours,
                )
                for record in records
            ),
            page=page,
            page_size=page_size,
            total=total,
        )


def _activity_view(
    record: KnowledgeSourceActivityRecord,
    created_by: UserReference | None,
    staging_retention_hours: int,
) -> KnowledgeSourceActivityView:
    source = record.source
    return KnowledgeSourceActivityView(
        id=source.id,
        title=source.title,
        original_filename=source.original_filename,
        content_type=source.content_type,
        size_bytes=source.declared_size_bytes,
        change_kind="replace" if source.target_document_id else "create",
        status=source.status,
        document_id=record.document_id,
        attempts=record.attempts,
        error_code=record.error_code,
        created_by_display_name=record.created_by_display_name,
        created_by_user=created_by,
        staging_expires_at=(
            source.created_at + timedelta(hours=staging_retention_hours)
            if source.status == "staging"
            else None
        ),
        created_at=source.created_at,
        updated_at=source.updated_at,
    )
