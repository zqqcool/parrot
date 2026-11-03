from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.agents.models import AgentPublication
from app.modules.agents.ports import AgentRuntimeTarget


class AgentCatalog:
    """Public read interface for modules that reference agents."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def exists(self, tenant_id: str, agent_id: str) -> bool:
        value = await self.session.scalar(
            select(AgentPublication.id).where(
                AgentPublication.tenant_id == tenant_id,
                AgentPublication.id == agent_id,
            )
        )
        return value is not None

    async def get_published(self, tenant_id: str, agent_id: str) -> AgentRuntimeTarget | None:
        item = await self.session.scalar(
            select(AgentPublication).where(
                AgentPublication.tenant_id == tenant_id,
                AgentPublication.id == agent_id,
                AgentPublication.status == "active",
                AgentPublication.published.is_(True),
            )
        )
        if item is None:
            return None
        return AgentRuntimeTarget(
            id=item.id,
            tenant_id=item.tenant_id,
            runtime_agent_id=item.runtime_agent_id,
        )

    async def get_anonymous_target(
        self, tenant_id: str, agent_id: str
    ) -> AgentRuntimeTarget | None:
        item = await self.session.scalar(
            select(AgentPublication).where(
                AgentPublication.tenant_id == tenant_id,
                AgentPublication.id == agent_id,
                AgentPublication.status == "active",
                AgentPublication.published.is_(True),
                AgentPublication.allow_anonymous.is_(True),
            )
        )
        if item is None:
            return None
        return AgentRuntimeTarget(
            id=item.id,
            tenant_id=item.tenant_id,
            runtime_agent_id=item.runtime_agent_id,
        )

    async def get_anonymous_target_by_slug(self, slug: str) -> AgentRuntimeTarget | None:
        item = await self.session.scalar(
            select(AgentPublication).where(
                AgentPublication.slug == slug,
                AgentPublication.status == "active",
                AgentPublication.published.is_(True),
                AgentPublication.allow_anonymous.is_(True),
            )
        )
        if item is None:
            return None
        return AgentRuntimeTarget(
            id=item.id,
            tenant_id=item.tenant_id,
            runtime_agent_id=item.runtime_agent_id,
        )

    async def names(self, tenant_id: str, agent_ids: tuple[str, ...]) -> dict[str, str]:
        if not agent_ids:
            return {}
        rows = await self.session.execute(
            select(AgentPublication.id, AgentPublication.name).where(
                AgentPublication.tenant_id == tenant_id,
                AgentPublication.id.in_(agent_ids),
            )
        )
        return dict(rows.tuples().all())
