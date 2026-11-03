from __future__ import annotations

from collections import defaultdict

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.agents.models import AgentPublication, AgentSkillBinding
from app.modules.skills.bound_agents import SkillBoundAgent


class AgentSkillUsage:
    """Provides the Skill module a narrow, read-only binding check."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def is_bound_to_agent(self, tenant_id: str, skill_id: str) -> bool:
        binding = await self.session.scalar(
            select(AgentSkillBinding.agent_id).where(
                AgentSkillBinding.tenant_id == tenant_id,
                AgentSkillBinding.skill_id == skill_id,
            )
        )
        return binding is not None

    async def list_bound_agents(
        self, tenant_id: str, skill_ids: tuple[str, ...]
    ) -> dict[str, tuple[SkillBoundAgent, ...]]:
        if not skill_ids:
            return {}
        rows = await self.session.execute(
            select(
                AgentSkillBinding.skill_id,
                AgentPublication.id,
                AgentPublication.name,
            )
            .join(
                AgentPublication,
                and_(
                    AgentPublication.tenant_id == AgentSkillBinding.tenant_id,
                    AgentPublication.id == AgentSkillBinding.agent_id,
                ),
            )
            .where(
                AgentSkillBinding.tenant_id == tenant_id,
                AgentSkillBinding.skill_id.in_(skill_ids),
            )
            .order_by(AgentSkillBinding.skill_id, AgentPublication.name, AgentPublication.id)
        )
        bound_agents: defaultdict[str, list[SkillBoundAgent]] = defaultdict(list)
        for skill_id, agent_id, name in rows.all():
            bound_agents[skill_id].append(
                SkillBoundAgent(
                    id=agent_id,
                    name=name,
                )
            )
        return {skill_id: tuple(agents) for skill_id, agents in bound_agents.items()}
