from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.knowledge.models import (
    AgentKnowledgeSpaceBinding,
    KnowledgeDocument,
    KnowledgeSource,
    KnowledgeSpace,
)


@dataclass(frozen=True)
class KnowledgeSpaceDeleteBlockers:
    document_count: int
    source_count: int
    agent_binding_count: int

    @property
    def blocked(self) -> bool:
        return any((self.document_count, self.source_count, self.agent_binding_count))


class KnowledgeSpaceDeletionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_space_for_update(self, tenant_id: str, space_id: str) -> KnowledgeSpace | None:
        return await self.session.scalar(
            select(KnowledgeSpace)
            .where(KnowledgeSpace.tenant_id == tenant_id, KnowledgeSpace.id == space_id)
            .with_for_update()
        )

    async def blockers(self, tenant_id: str, space_id: str) -> KnowledgeSpaceDeleteBlockers:
        document_count_query = (
            select(func.count())
            .select_from(KnowledgeDocument)
            .where(
                KnowledgeDocument.tenant_id == tenant_id,
                KnowledgeDocument.space_id == space_id,
            )
            .scalar_subquery()
        )
        source_count_query = (
            select(func.count())
            .select_from(KnowledgeSource)
            .where(KnowledgeSource.tenant_id == tenant_id, KnowledgeSource.space_id == space_id)
            .scalar_subquery()
        )
        agent_binding_count_query = (
            select(func.count())
            .select_from(AgentKnowledgeSpaceBinding)
            .where(
                AgentKnowledgeSpaceBinding.tenant_id == tenant_id,
                AgentKnowledgeSpaceBinding.space_id == space_id,
            )
            .scalar_subquery()
        )
        document_count, source_count, agent_binding_count = (
            await self.session.execute(
                select(
                    document_count_query,
                    source_count_query,
                    agent_binding_count_query,
                )
            )
        ).one()
        return KnowledgeSpaceDeleteBlockers(
            document_count=int(document_count),
            source_count=int(source_count),
            agent_binding_count=int(agent_binding_count),
        )

    async def delete_space(self, tenant_id: str, space_id: str) -> None:
        await self.session.execute(
            delete(KnowledgeSpace).where(
                KnowledgeSpace.tenant_id == tenant_id,
                KnowledgeSpace.id == space_id,
            )
        )
