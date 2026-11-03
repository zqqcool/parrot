from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.errors import AppError
from app.infrastructure.db.session import DatabaseManager
from app.modules.audit.service import append_audit
from app.modules.iam.schemas import PrincipalContext
from app.modules.knowledge.access import KnowledgeAccessPolicy
from app.modules.knowledge.models import KnowledgeSpace
from app.modules.knowledge.repository import KnowledgeRepository
from app.modules.knowledge.space_deletion_repository import (
    KnowledgeSpaceDeleteBlockers,
    KnowledgeSpaceDeletionRepository,
)


class KnowledgeSpaceDeletionService:
    def __init__(self, session: AsyncSession, database: DatabaseManager) -> None:
        self.session = session
        self.access_policy = KnowledgeAccessPolicy(session, database)
        self.spaces = KnowledgeRepository(session)
        self.repository = KnowledgeSpaceDeletionRepository(session)

    async def delete_space(
        self, principal: PrincipalContext, tenant_id: str, space_id: str
    ) -> None:
        await self.access_policy.enter(
            principal,
            tenant_id,
            "knowledge.spaces.manage",
            not_found_message="Knowledge space not found",
        )
        space = await self._locked_visible_space(principal, tenant_id, space_id)
        blockers = await self.repository.blockers(tenant_id, space_id)
        if blockers.blocked:
            raise _not_empty_error(blockers)
        await self.repository.delete_space(tenant_id, space_id)
        append_audit(
            self.session,
            principal,
            "knowledge.space.delete",
            "knowledge_space",
            space.id,
            {"name": space.name, "slug": space.slug},
            tenant_id=tenant_id,
        )
        await self.session.flush()

    async def _locked_visible_space(
        self, principal: PrincipalContext, tenant_id: str, space_id: str
    ) -> KnowledgeSpace:
        space = await self.repository.get_space_for_update(tenant_id, space_id)
        if (
            space is None
            or space.status != "active"
            or not await self.spaces.user_has_access(tenant_id, space_id, principal.subject_id)
        ):
            raise AppError(
                "RESOURCE_NOT_FOUND", "Knowledge space not found", status.HTTP_404_NOT_FOUND
            )
        return space


def _not_empty_error(blockers: KnowledgeSpaceDeleteBlockers) -> AppError:
    details: list[dict[str, str]] = []
    if blockers.document_count:
        details.append({"field": "documents", "reason": str(blockers.document_count)})
    if blockers.source_count:
        details.append({"field": "sources", "reason": str(blockers.source_count)})
    if blockers.agent_binding_count:
        details.append({"field": "agent_bindings", "reason": str(blockers.agent_binding_count)})
    return AppError(
        "KNOWLEDGE_SPACE_NOT_EMPTY",
        "Knowledge space still contains content or Agent bindings",
        status.HTTP_409_CONFLICT,
        details,
    )
