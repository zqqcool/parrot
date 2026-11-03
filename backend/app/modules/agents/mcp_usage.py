from __future__ import annotations

from collections import defaultdict

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.agents.models import AgentMcpServerBinding, AgentPublication
from app.modules.mcp_servers.bound_agents import McpBoundAgent


class AgentMcpUsage:
    """Provides the MCP module a narrow, read-only binding lookup."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_bound_agents(
        self, tenant_id: str, server_ids: tuple[str, ...]
    ) -> dict[str, tuple[McpBoundAgent, ...]]:
        if not server_ids:
            return {}
        rows = await self.session.execute(
            select(
                AgentMcpServerBinding.mcp_server_id,
                AgentPublication.id,
                AgentPublication.name,
            )
            .join(
                AgentPublication,
                and_(
                    AgentPublication.tenant_id == AgentMcpServerBinding.tenant_id,
                    AgentPublication.id == AgentMcpServerBinding.agent_id,
                ),
            )
            .where(
                AgentMcpServerBinding.tenant_id == tenant_id,
                AgentMcpServerBinding.mcp_server_id.in_(server_ids),
            )
            .order_by(
                AgentMcpServerBinding.mcp_server_id,
                AgentPublication.name,
                AgentPublication.id,
            )
        )
        bound_agents: defaultdict[str, list[McpBoundAgent]] = defaultdict(list)
        for server_id, agent_id, name in rows.all():
            bound_agents[server_id].append(McpBoundAgent(id=agent_id, name=name))
        return {server_id: tuple(agents) for server_id, agents in bound_agents.items()}
