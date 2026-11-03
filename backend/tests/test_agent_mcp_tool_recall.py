from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.infrastructure.db.session import DatabaseManager
from app.modules.agent_runtime.mcp_executor import McpExecutor, RuntimeMcpTool
from app.modules.agents.mcp_tool_recall_service import AgentMcpToolRecallService
from app.modules.agents.schemas import AgentMcpToolRecallRequest
from app.modules.capability_index.hybrid_search import (
    CapabilitySearchEvaluator,
    CapabilitySearchOutcome,
)
from app.modules.iam.schemas import PrincipalContext
from app.modules.mcp_servers.models import McpServer
from app.modules.mcp_servers.tool_policy import mcp_schema_hash


@pytest.mark.asyncio
async def test_agent_mcp_tool_recall_reuses_runtime_scope_and_policy_filter() -> None:
    schema: dict[str, object] = {
        "type": "object",
        "properties": {"query": {"type": "string"}},
    }
    remote = _server(
        "mcp_docs",
        tool_policies=[
            {
                "name": "search_docs",
                "description": "Search documentation",
                "input_schema": schema,
                "schema_hash": mcp_schema_hash(schema),
                "effect": "read",
                "approval": "automatic",
            },
            {
                "name": "write_ticket",
                "description": "Create a ticket",
                "input_schema": schema,
                "schema_hash": mcp_schema_hash(schema),
                "effect": "side_effect",
                "approval": "required",
            },
        ],
    )
    local = _server("mcp_local", transport="stdio", endpoint="local-mcp")
    allowed = _tool(remote, "search_docs", "Search documentation", schema=schema)
    write_tool = _tool(remote, "write_ticket", "Create a ticket", schema=schema)
    hint_only = _tool(remote, "unapproved_tool", "Unapproved tool", read_only=True)
    session = SimpleNamespace(
        scalar=AsyncMock(side_effect=("agent_test", "knowledge", 0.4)),
        scalars=AsyncMock(side_effect=((remote.id, local.id), (remote, local))),
    )
    database = SimpleNamespace(set_tenant=AsyncMock())
    ranker = SimpleNamespace(
        evaluate=AsyncMock(
            return_value=CapabilitySearchOutcome(
                (write_tool.capability_id, allowed.capability_id),
                "hybrid",
                (
                    (write_tool.capability_id, 0.86),
                    (allowed.capability_id, 0.81),
                ),
            )
        )
    )
    executor = SimpleNamespace(discover=AsyncMock(return_value=(allowed, write_tool, hint_only)))
    service = AgentMcpToolRecallService(
        cast(AsyncSession, session),
        cast(DatabaseManager, database),
        cast(CapabilitySearchEvaluator, ranker),
        cast(McpExecutor, executor),
    )

    result = await service.search(
        _principal("agents.read", "mcp_servers.read"),
        "tenant_test",
        "agent_test",
        AgentMcpToolRecallRequest(query="  查询入住说明  ", relevance_threshold=0.6),
    )

    assert result.query == "查询入住说明"
    assert result.eligible_server_count == 1
    assert result.eligible_tool_count == 2
    assert result.configured_relevance_threshold == 0.4
    assert result.applied_relevance_threshold == 0.6
    assert result.candidates[0].id == write_tool.capability_id
    assert result.candidates[0].relevance_score == 0.86
    discovered_servers = executor.discover.await_args.args[0]
    assert [(server.id, server.transport) for server in discovered_servers] == [
        (remote.id, "streamable_http")
    ]
    documents = ranker.evaluate.await_args.args[2]
    assert len(documents) == 2
    assert "server: Docs MCP" in documents[0].text
    assert "tool: search_docs" in documents[0].text
    assert "tool: write_ticket" in documents[1].text
    assert ranker.evaluate.await_args.kwargs == {"minimum_relevance_score": 0.6}
    assert database.set_tenant.await_count == 2


def test_agent_mcp_tool_recall_threshold_must_be_a_probability() -> None:
    with pytest.raises(ValueError):
        AgentMcpToolRecallRequest(query="search docs", relevance_threshold=-0.01)


@pytest.mark.asyncio
async def test_agent_mcp_tool_recall_requires_mcp_read_permission() -> None:
    session = SimpleNamespace(scalar=AsyncMock(), scalars=AsyncMock())
    database = SimpleNamespace(set_tenant=AsyncMock())
    ranker = SimpleNamespace(evaluate=AsyncMock())
    executor = SimpleNamespace(discover=AsyncMock())
    service = AgentMcpToolRecallService(
        cast(AsyncSession, session),
        cast(DatabaseManager, database),
        cast(CapabilitySearchEvaluator, ranker),
        cast(McpExecutor, executor),
    )

    with pytest.raises(AppError) as captured:
        await service.search(
            _principal("agents.read"),
            "tenant_test",
            "agent_test",
            AgentMcpToolRecallRequest(query="search docs"),
        )

    assert captured.value.code == "FORBIDDEN"
    session.scalar.assert_not_awaited()
    executor.discover.assert_not_awaited()


def _server(
    server_id: str,
    *,
    transport: str = "streamable_http",
    endpoint: str = "https://mcp.example.test",
    tool_policies: list[dict[str, object]] | None = None,
) -> McpServer:
    return McpServer(
        id=server_id,
        tenant_id="tenant_test",
        name="Docs MCP" if server_id == "mcp_docs" else "Local MCP",
        transport=transport,
        endpoint=endpoint,
        arguments=[],
        encrypted_credentials=[],
        tool_policies=tool_policies or [],
        status="active",
    )


def _tool(
    server: McpServer,
    name: str,
    description: str,
    *,
    schema: dict[str, object] | None = None,
    read_only: bool = False,
) -> RuntimeMcpTool:
    return RuntimeMcpTool(
        capability_id=f"mcp:{server.id}:{name}",
        server_id=server.id,
        server_name=server.name,
        tool_name=name,
        description=description,
        input_schema=schema or {"type": "object"},
        read_only=read_only,
    )


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
