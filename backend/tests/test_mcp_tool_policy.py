from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
from _agent_runtime_support import credential_cipher
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent_runtime import RuntimeMcpServerProfile, RuntimeMcpToolPolicy
from app.infrastructure.db.session import DatabaseManager
from app.modules.agent_runtime.capabilities import CapabilitySession
from app.modules.agent_runtime.contracts import ToolCall
from app.modules.agent_runtime.mcp_executor import McpExecutor, RuntimeMcpTool
from app.modules.iam.schemas import PrincipalContext
from app.modules.mcp_servers.models import McpServer
from app.modules.mcp_servers.schemas import McpServerCreateRequest, McpToolPolicyInput
from app.modules.mcp_servers.service import McpServerService
from app.modules.mcp_servers.tool_policy import (
    arguments_match_schema,
    automatic_read_policy,
    enabled_tool_policy,
    mcp_schema_hash,
    parallel_safe_policy,
)


def test_mcp_schema_hash_is_canonical_and_arguments_are_validated() -> None:
    first: dict[str, object] = {
        "type": "object",
        "properties": {"query": {"type": "string"}},
    }
    second: dict[str, object] = {
        "properties": {"query": {"type": "string"}},
        "type": "object",
    }

    assert mcp_schema_hash(first) == mcp_schema_hash(second)
    assert arguments_match_schema({"query": "release"}, first)
    assert not arguments_match_schema({"query": 123}, first)


def test_mcp_policy_rejects_automatic_side_effects() -> None:
    with pytest.raises(ValidationError, match="Only read-only MCP tools can be automatic"):
        McpToolPolicyInput.model_validate(
            {
                "name": "create_ticket",
                "description": "Create a ticket",
                "input_schema": {"type": "object"},
                "effect": "side_effect",
                "approval": "automatic",
            }
        )


def test_parallel_safe_policy_requires_an_automatic_read() -> None:
    policy = McpToolPolicyInput.model_validate(
        {
            "name": "search",
            "input_schema": {"type": "object"},
            "effect": "read",
            "approval": "automatic",
            "parallel_safe": True,
        }
    )
    assert policy.parallel_safe is True

    with pytest.raises(ValidationError, match="parallel-safe"):
        McpToolPolicyInput.model_validate(
            {
                "name": "search_sensitive",
                "input_schema": {"type": "object"},
                "effect": "read",
                "approval": "required",
                "parallel_safe": True,
            }
        )


def test_parallel_safe_policy_rechecks_live_schema_and_server_policy() -> None:
    schema: dict[str, object] = {"type": "object"}
    tool = RuntimeMcpTool(
        capability_id="mcp:docs:search",
        server_id="docs",
        server_name="Docs",
        tool_name="search",
        description="Search",
        input_schema=schema,
        read_only=True,
    )
    server = RuntimeMcpServerProfile(
        id="docs",
        name="Docs",
        transport="streamable_http",
        endpoint="https://example.test/mcp",
        arguments=(),
        encrypted_credentials=(),
        tool_policies=(
            RuntimeMcpToolPolicy(
                name="search",
                description="Search",
                input_schema=schema,
                schema_hash=mcp_schema_hash(schema),
                effect="read",
                approval="automatic",
                parallel_safe=True,
            ),
        ),
    )

    assert parallel_safe_policy(server, tool) is not None


@pytest.mark.asyncio
async def test_capability_session_exposes_only_discovered_parallel_safe_calls() -> None:
    schema: dict[str, object] = {"type": "object"}
    tool = RuntimeMcpTool(
        capability_id="mcp:docs:search",
        server_id="docs",
        server_name="Docs",
        tool_name="search",
        description="Search",
        input_schema=schema,
        read_only=True,
    )
    server = RuntimeMcpServerProfile(
        id="docs",
        name="Docs",
        transport="streamable_http",
        endpoint="https://example.test/mcp",
        arguments=(),
        encrypted_credentials=(),
        tool_policies=(
            RuntimeMcpToolPolicy(
                name="search",
                description="Search",
                input_schema=schema,
                schema_hash=mcp_schema_hash(schema),
                effect="read",
                approval="automatic",
                parallel_safe=True,
            ),
        ),
    )
    executor = cast(
        McpExecutor,
        SimpleNamespace(discover=AsyncMock(return_value=(tool,))),
    )
    session = CapabilitySession((), mcp_servers=(server,), mcp_executor=executor)

    await session.search("find", "", None)

    assert session.is_parallel_safe_call(
        ToolCall(
            id="call_search",
            name="capability_execute",
            arguments={"capability_id": tool.capability_id, "input": {}},
        )
    )


def test_mcp_policy_rejects_invalid_schemas_and_duplicate_names() -> None:
    with pytest.raises(ValidationError, match="valid JSON Schema"):
        McpToolPolicyInput.model_validate(
            {
                "name": "search",
                "input_schema": {"type": "not-a-json-schema-type"},
                "effect": "read",
                "approval": "automatic",
            }
        )
    policy = {
        "name": "search",
        "input_schema": {"type": "object"},
        "effect": "read",
        "approval": "automatic",
    }
    with pytest.raises(ValidationError, match="must be unique"):
        McpServerCreateRequest.model_validate(
            {
                "name": "Docs",
                "transport": "streamable_http",
                "endpoint": "https://mcp.example.test",
                "tool_policies": [policy, policy],
            }
        )


def test_automatic_policy_fails_closed_when_the_live_schema_changes() -> None:
    snapshot: dict[str, object] = {"type": "object", "required": ["query"]}
    server = RuntimeMcpServerProfile(
        id="mcp_docs",
        name="Docs",
        transport="streamable_http",
        endpoint="https://mcp.example.test",
        arguments=(),
        encrypted_credentials=(),
        tool_policies=(
            RuntimeMcpToolPolicy(
                name="search",
                description="Search docs",
                input_schema=snapshot,
                schema_hash=mcp_schema_hash(snapshot),
                effect="read",
                approval="automatic",
            ),
        ),
    )
    changed = RuntimeMcpTool(
        capability_id="mcp:mcp_docs:search",
        server_id="mcp_docs",
        server_name="Docs",
        tool_name="search",
        description="Search docs",
        input_schema={"type": "object", "required": ["term"]},
        read_only=True,
    )

    assert automatic_read_policy(server, changed) is None


def test_enabled_policy_fails_closed_for_an_invalid_automatic_side_effect() -> None:
    schema: dict[str, object] = {"type": "object"}
    tool = RuntimeMcpTool(
        capability_id="mcp:mcp_ticket:create",
        server_id="mcp_ticket",
        server_name="Ticket MCP",
        tool_name="create",
        description="Create ticket",
        input_schema=schema,
        read_only=False,
    )
    server = RuntimeMcpServerProfile(
        id="mcp_ticket",
        name="Ticket MCP",
        transport="streamable_http",
        endpoint="https://mcp.example.test",
        arguments=(),
        encrypted_credentials=(),
        tool_policies=(
            RuntimeMcpToolPolicy(
                name=tool.tool_name,
                description=tool.description,
                input_schema=schema,
                schema_hash=mcp_schema_hash(schema),
                effect="side_effect",
                approval="automatic",
            ),
        ),
    )

    assert enabled_tool_policy(server, tool) is None


@pytest.mark.asyncio
async def test_management_discovery_returns_a_server_computed_schema_hash() -> None:
    model = McpServer(
        id="mcp_docs",
        tenant_id="tenant_test",
        name="Docs",
        transport="streamable_http",
        endpoint="https://mcp.example.test",
        arguments=[],
        encrypted_credentials=[],
        tool_policies=[],
        status="active",
    )
    schema: dict[str, object] = {
        "type": "object",
        "properties": {"query": {"type": "string"}},
    }
    tool = RuntimeMcpTool(
        capability_id="mcp:mcp_docs:search",
        server_id="mcp_docs",
        server_name="Docs",
        tool_name="search",
        description="Search docs",
        input_schema=schema,
        read_only=True,
    )
    executor = SimpleNamespace(discover=AsyncMock(return_value=(tool,)))
    session = cast(AsyncSession, SimpleNamespace(scalar=AsyncMock(return_value=model)))
    database = cast(DatabaseManager, SimpleNamespace(set_tenant=AsyncMock()))
    service = McpServerService(
        session,
        database,
        credential_cipher(),
        mcp_executor=cast(McpExecutor, executor),
    )

    result = await service.discover_tools(_principal(), "tenant_test", model.id)

    assert result[0].schema_hash == mcp_schema_hash(schema)
    assert result[0].read_only_hint is True
    executor.discover.assert_awaited_once()


def _principal() -> PrincipalContext:
    return PrincipalContext(
        tenant_id="tenant_test",
        subject_id="user_test",
        username="admin",
        display_name="Admin",
        permissions=("mcp_servers.manage",),
        tenants=(),
        must_change_password=False,
        request_id="request_test",
    )
