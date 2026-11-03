from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.agents.models import AgentPublication
from app.modules.interactions.models import Interaction
from app.modules.llm_configs.models import LlmConfig
from app.modules.mcp_servers.models import McpServer
from app.modules.skills.models import Skill


class DashboardRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def count_agents(self, tenant_id: str) -> int:
        result = await self.session.scalar(
            select(func.count())
            .select_from(AgentPublication)
            .where(AgentPublication.tenant_id == tenant_id)
        )
        return int(result or 0)

    async def count_im_entries(self, tenant_id: str) -> int:
        result = await self.session.scalar(
            select(func.count())
            .select_from(AgentPublication)
            .where(
                AgentPublication.tenant_id == tenant_id,
                AgentPublication.status == "active",
                AgentPublication.published.is_(True),
                AgentPublication.allow_anonymous.is_(True),
            )
        )
        return int(result or 0)

    async def count_capability_configs(self, tenant_id: str) -> tuple[int, int, int]:
        counts: list[int] = []
        for model in (LlmConfig, Skill, McpServer):
            value = await self.session.scalar(
                select(func.count()).select_from(model).where(model.tenant_id == tenant_id)
            )
            counts.append(int(value or 0))
        return counts[0], counts[1], counts[2]

    async def count_runs(self, tenant_id: str) -> tuple[int, int]:
        total = await self.session.scalar(
            select(func.count()).select_from(Interaction).where(Interaction.tenant_id == tenant_id)
        )
        active = await self.session.scalar(
            select(func.count())
            .select_from(Interaction)
            .where(
                Interaction.tenant_id == tenant_id,
                Interaction.status.in_(("accepted", "running", "waiting_user_input")),
            )
        )
        return int(total or 0), int(active or 0)
