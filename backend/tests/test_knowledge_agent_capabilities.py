from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
from _agent_runtime_support import profile

from app.core.agent_runtime import (
    RuntimeMcpServerProfile,
    RuntimeMcpToolPolicy,
    RuntimeSkillProfile,
)
from app.modules.agent_runtime.active_skill import SkillContextCheckpointPort
from app.modules.agent_runtime.capabilities import CapabilitySession
from app.modules.agent_runtime.mcp_executor import McpExecutor, RuntimeMcpTool
from app.modules.agent_runtime.skill_executor import SkillExecutionContext, SkillExecutor
from app.modules.agents.repository import AgentBindingRepository
from app.modules.agents.runtime_profile import BoundAgentRuntimeProfileResolver
from app.modules.interactions.runtime import RuntimeActiveSkill, RuntimeSkillContext
from app.modules.llm_configs.runtime_catalog import LlmRuntimeCatalog
from app.modules.mcp_servers.runtime_catalog import McpRuntimeCatalog
from app.modules.mcp_servers.tool_policy import mcp_schema_hash
from app.modules.skills.runtime_catalog import SkillRuntimeCatalog


@pytest.mark.asyncio
async def test_knowledge_capability_session_rejects_executable_skills() -> None:
    executable = RuntimeSkillProfile(
        id="skill_executable",
        name="unsafe",
        description="unsafe",
        instructions="",
        manifest={"runtime": {"type": "python", "entrypoint": "run.py"}},
        version=1,
    )
    session = CapabilitySession((*profile().skills, executable), knowledge_only=True)

    found = await session.search("find", "", None)
    capabilities = cast(list[dict[str, object]], found["capabilities"])

    assert [item["id"] for item in capabilities] == ["skill_test"]
    assert (await session.search("load", None, executable.id))[
        "code"
    ] == "KNOWLEDGE_CAPABILITY_NOT_ALLOWED"


@pytest.mark.asyncio
async def test_knowledge_instruction_skill_does_not_start_the_sandbox() -> None:
    executor = SimpleNamespace(execute=AsyncMock())
    instruction_skill = profile().skills[0]
    session = CapabilitySession(
        (instruction_skill,),
        skill_executor=cast(SkillExecutor, executor),
        knowledge_only=True,
    )

    await session.search("load", None, instruction_skill.id)
    result = await session.execute(instruction_skill.id)

    assert result["status"] == "instruction_ready"
    executor.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_primary_skill_session_can_load_and_execute_a_supporting_skill() -> None:
    active = profile().skills[0]
    other = replace(active, id="skill_other", name="other")
    session = CapabilitySession(
        (active, other),
        loaded_skill_ids={active.id},
        active_skill=RuntimeActiveSkill(active.id, active.version),
        knowledge_only=True,
    )

    found = await session.search("find", "other", None)
    loaded = await session.search("load", None, other.id, "supporting")
    executed = await session.execute(other.id)

    assert other.id in [item["id"] for item in cast(list[dict[str, object]], found["capabilities"])]
    assert loaded["status"] == "ok"
    assert loaded["role"] == "supporting"
    assert executed["status"] == "instruction_ready"


@pytest.mark.asyncio
async def test_supporting_skill_load_persists_the_skill_context_checkpoint() -> None:
    primary = profile().skills[0]
    supporting = replace(primary, id="skill_supporting", name="supporting")
    persisted_context = RuntimeSkillContext(
        primary=RuntimeActiveSkill(primary.id, primary.version),
        supporting=(RuntimeActiveSkill(supporting.id, supporting.version),),
    )
    checkpoints = SimpleNamespace(pin=AsyncMock(return_value=persisted_context))
    session = CapabilitySession(
        (primary, supporting),
        loaded_skill_ids={primary.id},
        active_skill=RuntimeActiveSkill(primary.id, primary.version),
        skill_context_checkpoints=cast(SkillContextCheckpointPort, checkpoints),
        execution_context=SkillExecutionContext(
            tenant_id="tenant_test",
            interaction_id="interaction_test",
            actor_type="anonymous",
            actor_id="visitor_test",
            request_id="request_test",
        ),
        knowledge_only=True,
    )

    result = await session.search("load", None, supporting.id, "supporting")

    assert result["status"] == "ok"
    assert session.skill_context == persisted_context
    checkpoints.pin.assert_awaited_once_with(
        tenant_id="tenant_test",
        interaction_id="interaction_test",
        role="supporting",
        skill_id=supporting.id,
        skill_version=supporting.version,
    )


@pytest.mark.asyncio
async def test_supporting_skill_load_respects_the_configured_limit() -> None:
    primary = profile().skills[0]
    first = replace(primary, id="skill_first", name="first")
    second = replace(primary, id="skill_second", name="second")
    session = CapabilitySession(
        (primary, first, second),
        loaded_skill_ids={primary.id},
        active_skill=RuntimeActiveSkill(primary.id, primary.version),
        max_supporting_skills=1,
        knowledge_only=True,
    )

    loaded = await session.search("load", None, first.id, "supporting")
    rejected = await session.search("load", None, second.id, "supporting")

    assert loaded["status"] == "ok"
    assert rejected["status"] == "rejected"
    assert rejected["code"] == "SKILL_CONTEXT_CONFLICT"


@pytest.mark.asyncio
async def test_active_skill_session_can_execute_an_approved_mcp_tool() -> None:
    active = profile().skills[0]
    read_tool = _mcp_tool(read_only=True, name="read")
    remote_server = replace(
        _remote_server(),
        tool_policies=(
            RuntimeMcpToolPolicy(
                name=read_tool.tool_name,
                description=read_tool.description,
                input_schema=read_tool.input_schema,
                schema_hash=mcp_schema_hash(read_tool.input_schema),
                effect="read",
                approval="automatic",
            ),
        ),
    )
    executor = SimpleNamespace(
        discover=AsyncMock(return_value=(read_tool,)),
        execute=AsyncMock(return_value={"status": "succeeded"}),
    )
    session = CapabilitySession(
        (active,),
        mcp_servers=(remote_server,),
        loaded_skill_ids={active.id},
        active_skill=RuntimeActiveSkill(active.id, active.version),
        mcp_executor=cast(McpExecutor, executor),
        knowledge_only=True,
    )

    result = await session.execute(read_tool.capability_id, {})

    assert result["status"] == "succeeded"
    executor.execute.assert_awaited_once_with(read_tool, {})


@pytest.mark.asyncio
async def test_knowledge_capability_session_discovers_approved_remote_mcp() -> None:
    remote_server = _remote_server()
    stdio_server = replace(
        remote_server,
        id="server_stdio",
        name="local",
        transport="stdio",
        endpoint="python",
    )
    read_tool = _mcp_tool(read_only=True, name="read")
    write_tool = _mcp_tool(read_only=False, name="write")
    forbidden_tool = _mcp_tool(read_only=False, name="forbidden")
    executor = SimpleNamespace(
        discover=AsyncMock(return_value=(read_tool, write_tool, forbidden_tool)),
        execute=AsyncMock(return_value={"status": "succeeded"}),
    )
    remote_server = replace(
        remote_server,
        tool_policies=(
            RuntimeMcpToolPolicy(
                name=read_tool.tool_name,
                description=read_tool.description,
                input_schema=read_tool.input_schema,
                schema_hash=mcp_schema_hash(read_tool.input_schema),
                effect="read",
                approval="automatic",
            ),
            RuntimeMcpToolPolicy(
                name=write_tool.tool_name,
                description=write_tool.description,
                input_schema=write_tool.input_schema,
                schema_hash=mcp_schema_hash(write_tool.input_schema),
                effect="side_effect",
                approval="required",
            ),
            RuntimeMcpToolPolicy(
                name=forbidden_tool.tool_name,
                description=forbidden_tool.description,
                input_schema=forbidden_tool.input_schema,
                schema_hash=mcp_schema_hash(forbidden_tool.input_schema),
                effect="side_effect",
                approval="forbidden",
            ),
        ),
    )
    session = CapabilitySession(
        (),
        mcp_servers=(remote_server, stdio_server),
        mcp_executor=cast(McpExecutor, executor),
        knowledge_only=True,
    )

    found = await session.search("find", "", None)
    capabilities = cast(list[dict[str, object]], found["capabilities"])

    assert [item["id"] for item in capabilities] == [
        read_tool.capability_id,
        write_tool.capability_id,
    ]
    write_result = await session.execute(write_tool.capability_id, {})
    assert write_result["status"] == "approval_required"
    assert write_result["code"] == "MCP_APPROVAL_REQUIRED"
    assert (await session.execute(forbidden_tool.capability_id, {}))["code"] == (
        "MCP_CAPABILITY_NOT_FOUND"
    )
    assert (await session.execute(read_tool.capability_id, {}))["status"] == "succeeded"
    executor.discover.assert_awaited_once_with((remote_server,))


@pytest.mark.asyncio
async def test_noninteractive_knowledge_session_hides_tools_that_require_confirmation() -> None:
    read_tool = _mcp_tool(read_only=True, name="read")
    write_tool = _mcp_tool(read_only=False, name="write")
    remote_server = replace(
        _remote_server(),
        tool_policies=(
            RuntimeMcpToolPolicy(
                name=read_tool.tool_name,
                description=read_tool.description,
                input_schema=read_tool.input_schema,
                schema_hash=mcp_schema_hash(read_tool.input_schema),
                effect="read",
                approval="automatic",
            ),
            RuntimeMcpToolPolicy(
                name=write_tool.tool_name,
                description=write_tool.description,
                input_schema=write_tool.input_schema,
                schema_hash=mcp_schema_hash(write_tool.input_schema),
                effect="side_effect",
                approval="required",
            ),
        ),
    )
    executor = SimpleNamespace(discover=AsyncMock(return_value=(read_tool, write_tool)))
    session = CapabilitySession(
        (),
        mcp_servers=(remote_server,),
        mcp_executor=cast(McpExecutor, executor),
        knowledge_only=True,
        approval_supported=False,
    )

    found = await session.search("find", "", None)

    assert [item["id"] for item in cast(list[dict[str, object]], found["capabilities"])] == [
        read_tool.capability_id
    ]
    assert (await session.execute(write_tool.capability_id, {}))["code"] == (
        "MCP_CAPABILITY_NOT_FOUND"
    )


@pytest.mark.asyncio
async def test_profile_resolver_filters_knowledge_capabilities_by_execution_type() -> None:
    llm = profile().llm
    instruction_skill = profile().skills[0]
    executable_skill = replace(
        instruction_skill,
        id="skill_executable",
        manifest={"runtime": {"type": "python", "entrypoint": "run.py"}},
    )
    remote_server = _remote_server()
    stdio_server = replace(
        remote_server,
        id="mcp_stdio",
        name="local",
        transport="stdio",
        endpoint="python",
    )
    bindings = _knowledge_bindings(
        llm.id,
        (instruction_skill.id, executable_skill.id),
        (remote_server.id, stdio_server.id),
    )
    resolver = BoundAgentRuntimeProfileResolver(
        cast(AgentBindingRepository, bindings),
        cast(LlmRuntimeCatalog, SimpleNamespace(get_active=AsyncMock(return_value=llm))),
        cast(
            SkillRuntimeCatalog,
            SimpleNamespace(
                get_published=AsyncMock(return_value=(instruction_skill, executable_skill))
            ),
        ),
        cast(
            McpRuntimeCatalog,
            SimpleNamespace(get_active=AsyncMock(return_value=(remote_server, stdio_server))),
        ),
    )

    resolved = await resolver.resolve("tenant_test", "agent_test")

    assert resolved.skills == (instruction_skill,)
    assert resolved.mcp_servers == (remote_server,)
    assert resolved.agent_type_key == "knowledge"


def _remote_server() -> RuntimeMcpServerProfile:
    return RuntimeMcpServerProfile(
        id="server_remote",
        name="remote",
        transport="streamable_http",
        endpoint="https://mcp.example.test",
        arguments=(),
        encrypted_credentials=(),
    )


def _mcp_tool(*, read_only: bool, name: str) -> RuntimeMcpTool:
    return RuntimeMcpTool(
        capability_id=f"mcp:server_remote:{name}",
        server_id="server_remote",
        server_name="docs",
        tool_name=name,
        description=f"{name.title()} a document",
        input_schema={},
        read_only=read_only,
    )


def _knowledge_bindings(
    llm_id: str, skill_ids: tuple[str, ...], server_ids: tuple[str, ...]
) -> SimpleNamespace:
    return SimpleNamespace(
        get_system_prompt=AsyncMock(return_value=""),
        get_agent_type_key=AsyncMock(return_value="knowledge"),
        get_llm_bindings=AsyncMock(return_value=((llm_id,), llm_id)),
        get_skill_bindings=AsyncMock(return_value=skill_ids),
        get_mcp_server_bindings=AsyncMock(return_value=server_ids),
    )
