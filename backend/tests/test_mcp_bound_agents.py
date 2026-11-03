from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.credential_cipher import CredentialCipher
from app.infrastructure.db.session import DatabaseManager
from app.modules.agents.mcp_usage import AgentMcpUsage
from app.modules.iam.schemas import PrincipalContext
from app.modules.mcp_servers.bound_agents import McpBoundAgent
from app.modules.mcp_servers.models import McpServer
from app.modules.mcp_servers.service import McpServerService


@pytest.mark.asyncio
async def test_agent_mcp_usage_groups_bound_agents_in_one_query() -> None:
    session = SimpleNamespace(
        execute=AsyncMock(
            return_value=SimpleNamespace(
                all=lambda: [
                    ("mcp_docs", "agent_assistant", "Docs Assistant"),
                    ("mcp_docs", "agent_ops", "Operations Assistant"),
                    ("mcp_search", "agent_search", "Search Assistant"),
                ]
            )
        )
    )

    result = await AgentMcpUsage(cast(AsyncSession, session)).list_bound_agents(
        "tenant_test", ("mcp_docs", "mcp_search")
    )

    assert result == {
        "mcp_docs": (
            McpBoundAgent("agent_assistant", "Docs Assistant"),
            McpBoundAgent("agent_ops", "Operations Assistant"),
        ),
        "mcp_search": (McpBoundAgent("agent_search", "Search Assistant"),),
    }
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_mcp_list_hides_bound_agents_without_agent_read_permission() -> None:
    reader = _BoundAgentReader()
    server = McpServer(
        id="mcp_docs",
        tenant_id="tenant_test",
        name="Docs",
        transport="streamable_http",
        endpoint="https://mcp.example.test",
        arguments=[],
        encrypted_credentials=[],
        status="active",
    )
    service = McpServerService(
        cast(AsyncSession, SimpleNamespace(scalars=AsyncMock(return_value=[server]))),
        cast(DatabaseManager, SimpleNamespace(set_tenant=AsyncMock())),
        cast(CredentialCipher, None),
        bound_agent_reader=reader,
    )

    without_permission = await service.list(_principal("mcp_servers.read"), "tenant_test")
    with_permission = await service.list(
        _principal("mcp_servers.read", "agents.read"), "tenant_test"
    )

    assert without_permission[0].bound_agents is None
    assert [agent.name for agent in with_permission[0].bound_agents or ()] == ["Docs"]
    assert reader.calls == [("tenant_test", ("mcp_docs",))]


class _BoundAgentReader:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    async def list_bound_agents(
        self, tenant_id: str, server_ids: tuple[str, ...]
    ) -> dict[str, tuple[McpBoundAgent, ...]]:
        self.calls.append((tenant_id, server_ids))
        return {"mcp_docs": (McpBoundAgent("agent_docs", "Docs"),)}


def _principal(*permissions: str) -> PrincipalContext:
    return PrincipalContext(
        tenant_id="tenant_test",
        subject_id="user_test",
        username="admin",
        display_name="Admin",
        permissions=permissions,
        tenants=(),
        must_change_password=False,
        request_id="req_test",
    )
