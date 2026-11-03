from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.agent_runtime import RuntimeMcpServerProfile
from app.core.agent_types import agent_type_policy
from app.core.errors import AppError
from app.infrastructure.db.session import DatabaseManager
from app.modules.agent_runtime.mcp_executor import McpExecutor, RuntimeMcpTool
from app.modules.agents.repository import AgentBindingRepository
from app.modules.agents.schemas import (
    AgentMcpToolRecallCandidateView,
    AgentMcpToolRecallRequest,
    AgentMcpToolRecallView,
)
from app.modules.capabilities.authorization import enter_tenant_capability_scope
from app.modules.capability_index.documents import mcp_tool_index_text
from app.modules.capability_index.hybrid_search import CapabilitySearchEvaluator
from app.modules.capability_index.ranking import CapabilitySearchDocument
from app.modules.iam.permissions import AGENTS_READ, MCP_SERVERS_READ
from app.modules.iam.schemas import PrincipalContext
from app.modules.mcp_servers.runtime_catalog import McpRuntimeCatalog
from app.modules.mcp_servers.tool_policy import enabled_tool_policy


class AgentMcpToolRecallService:
    """Discovers and ranks the Agent's runtime-eligible MCP tools without executing them."""

    def __init__(
        self,
        session: AsyncSession,
        database: DatabaseManager,
        search: CapabilitySearchEvaluator,
        mcp_executor: McpExecutor,
    ) -> None:
        self._session = session
        self._database = database
        self._search = search
        self._mcp_executor = mcp_executor
        self._bindings = AgentBindingRepository(session)
        self._servers = McpRuntimeCatalog(session)

    async def search(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        agent_id: str,
        payload: AgentMcpToolRecallRequest,
    ) -> AgentMcpToolRecallView:
        await self._enter(principal, tenant_id)
        if not await self._bindings.agent_exists(tenant_id, agent_id):
            raise AppError("RESOURCE_NOT_FOUND", "Agent not found", status.HTTP_404_NOT_FOUND)
        agent_type_key = await self._bindings.get_agent_type_key(tenant_id, agent_id)
        policy = agent_type_policy(agent_type_key) if agent_type_key is not None else None
        configured_threshold = await self._bindings.get_capability_relevance_threshold(
            tenant_id, agent_id
        )
        if (
            agent_type_key is None
            or policy is None
            or configured_threshold is None
            or not 0 <= configured_threshold <= 1
        ):
            raise self._invalid_runtime()
        applied_threshold = payload.relevance_threshold
        if applied_threshold is None:
            applied_threshold = configured_threshold
        server_ids = await self._bindings.get_mcp_server_bindings(tenant_id, agent_id)
        servers = await self._servers.get_active(tenant_id, server_ids)
        if len(servers) != len(server_ids):
            raise self._invalid_runtime()
        if not policy.allows_runtime_tools:
            servers = ()
        elif policy.uses_knowledge:
            servers = tuple(server for server in servers if not server.is_local_process)
        tools = await self._mcp_executor.discover(servers)
        if policy.uses_knowledge:
            tools = self._enabled_tools(servers, tools)
        outcome = await self._search.evaluate(
            tenant_id,
            payload.query,
            self._documents(tools),
            minimum_relevance_score=applied_threshold,
        )
        by_id = {tool.capability_id: tool for tool in tools}
        candidates = tuple(
            self._candidate(tool, rank, outcome.relevance_score_for(tool.capability_id))
            for rank, capability_id in enumerate(outcome.source_ids[:2], start=1)
            if (tool := by_id.get(capability_id)) is not None
        )
        return AgentMcpToolRecallView(
            agent_id=agent_id,
            agent_type_key=agent_type_key,
            query=payload.query,
            retrieval_method=outcome.retrieval_method,
            eligible_server_count=len(servers),
            eligible_tool_count=len(tools),
            configured_relevance_threshold=configured_threshold,
            applied_relevance_threshold=applied_threshold,
            candidates=candidates,
        )

    async def _enter(self, principal: PrincipalContext, tenant_id: str) -> None:
        await enter_tenant_capability_scope(
            self._database, self._session, principal, tenant_id, AGENTS_READ, "Agent"
        )
        await enter_tenant_capability_scope(
            self._database,
            self._session,
            principal,
            tenant_id,
            MCP_SERVERS_READ,
            "MCP server",
        )

    @staticmethod
    def _documents(tools: tuple[RuntimeMcpTool, ...]) -> tuple[CapabilitySearchDocument, ...]:
        return tuple(
            CapabilitySearchDocument(
                tool.capability_id,
                mcp_tool_index_text(tool.server_name, tool.tool_name, tool.description),
            )
            for tool in tools
        )

    @staticmethod
    def _enabled_tools(
        servers: tuple[RuntimeMcpServerProfile, ...], tools: tuple[RuntimeMcpTool, ...]
    ) -> tuple[RuntimeMcpTool, ...]:
        by_id = {server.id: server for server in servers}
        return tuple(
            tool
            for tool in tools
            if (server := by_id.get(tool.server_id)) is not None
            and enabled_tool_policy(server, tool) is not None
        )

    @staticmethod
    def _candidate(
        tool: RuntimeMcpTool, rank: int, relevance_score: float | None
    ) -> AgentMcpToolRecallCandidateView:
        return AgentMcpToolRecallCandidateView(
            id=tool.capability_id,
            server_id=tool.server_id,
            server_name=tool.server_name,
            name=tool.tool_name,
            description=tool.description,
            rank=rank,
            relevance_score=relevance_score,
        )

    @staticmethod
    def _invalid_runtime() -> AppError:
        return AppError(
            "AI_RUNTIME_CONFIGURATION_INVALID",
            "Agent runtime configuration is incomplete or unavailable",
            status.HTTP_409_CONFLICT,
        )
