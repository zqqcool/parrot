from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
from _agent_runtime_support import CapturingEvents, FakeModel, profile, request

from app.core.agent_runtime import RuntimeMcpServerProfile, RuntimeMcpToolPolicy
from app.modules.agent_runtime.capabilities import CapabilitySession
from app.modules.agent_runtime.contracts import ChatCompletion, ChatMessage, ToolCall
from app.modules.agent_runtime.in_process import InProcessAgentRuntime
from app.modules.agent_runtime.mcp_executor import McpExecutor, RuntimeMcpTool
from app.modules.agent_runtime.resume_snapshot import create_resume_snapshot
from app.modules.interactions.runtime import RuntimeRequest
from app.modules.mcp_servers.tool_policy import mcp_schema_hash


class RecordingPendingActions:
    def __init__(self) -> None:
        self.executions = 0
        self.results: list[dict[str, object]] = []

    async def prepare(
        self,
        request: RuntimeRequest,
        call: ToolCall,
        value: dict[str, object],
        messages: list[ChatMessage],
    ) -> dict[str, object]:
        del request, call, value, messages
        raise AssertionError("prepare is not expected while resuming an approval")

    async def mark_executing(self, request: object, action: dict[str, object]) -> bool:
        del request
        self.executions += 1
        action["status"] = "executing"
        return True

    async def mark_completed(
        self,
        request: RuntimeRequest,
        action: dict[str, object],
        result: dict[str, object],
    ) -> None:
        del request
        action["status"] = "completed"
        action["result"] = result
        self.results.append(result)


class PreparingPendingActions(RecordingPendingActions):
    def __init__(self) -> None:
        super().__init__()
        self.prepared: list[dict[str, object]] = []

    async def prepare(
        self,
        request: RuntimeRequest,
        call: ToolCall,
        value: dict[str, object],
        messages: list[ChatMessage],
    ) -> dict[str, object]:
        del request, call, messages
        self.prepared.append(value)
        return {
            "status": "waiting_approval",
            "code": "MCP_APPROVAL_REQUIRED",
            "action_id": "pending_1",
            "action_hash": "sha256:action",
            "version": "v1",
        }


@pytest.mark.asyncio
@pytest.mark.parametrize("knowledge_only", [False, True])
async def test_root_agent_requires_approval_for_a_discovered_write_mcp_tool(
    knowledge_only: bool,
) -> None:
    ticket_tool = RuntimeMcpTool(
        capability_id="mcp:mcp_test:create_ticket",
        server_id="mcp_test",
        server_name="Local ticket MCP",
        tool_name="create_ticket",
        description="Create a test ticket after confirmation",
        input_schema={"type": "object"},
        read_only=False,
    )
    executor = SimpleNamespace(
        discover=AsyncMock(return_value=(ticket_tool,)),
        execute=AsyncMock(return_value={"status": "succeeded", "result": {"status": "created"}}),
    )
    session = CapabilitySession(
        (),
        mcp_servers=(
            RuntimeMcpServerProfile(
                id="mcp_test",
                name="Local ticket MCP",
                transport="streamable_http",
                endpoint="http://127.0.0.1:8765/mcp",
                arguments=(),
                encrypted_credentials=(),
                tool_policies=(
                    RuntimeMcpToolPolicy(
                        name=ticket_tool.tool_name,
                        description=ticket_tool.description,
                        input_schema=ticket_tool.input_schema,
                        schema_hash=mcp_schema_hash(ticket_tool.input_schema),
                        effect="side_effect",
                        approval="required",
                    ),
                ),
            ),
        ),
        mcp_executor=cast(McpExecutor, executor),
        knowledge_only=knowledge_only,
    )

    found = await session.search("find", "create ticket", None)
    result = await session.execute(ticket_tool.capability_id, {"confirmed": True})

    assert found["status"] == "ok"
    assert result["status"] == "approval_required"
    assert result["code"] == "MCP_APPROVAL_REQUIRED"
    assert cast(dict[str, object], result["pending_action"])["schema_hash"] == (
        mcp_schema_hash(ticket_tool.input_schema)
    )
    executor.execute.assert_not_awaited()
    session.approval_supported = False
    unsupported = await session.execute(ticket_tool.capability_id, {"confirmed": True})
    assert unsupported["code"] == "MCP_APPROVAL_UNSUPPORTED"


@pytest.mark.asyncio
async def test_agent_loop_stops_on_a_durable_structured_approval() -> None:
    schema: dict[str, object] = {
        "type": "object",
        "properties": {"title": {"type": "string"}},
        "required": ["title"],
        "additionalProperties": False,
    }
    ticket_tool = RuntimeMcpTool(
        capability_id="mcp:mcp_test:create_ticket",
        server_id="mcp_test",
        server_name="Ticket MCP",
        tool_name="create_ticket",
        description="Create ticket",
        input_schema=schema,
        read_only=False,
    )
    mcp = SimpleNamespace(
        discover=AsyncMock(return_value=(ticket_tool,)),
        execute=AsyncMock(),
    )
    pending = PreparingPendingActions()
    model = FakeModel(
        [
            ChatCompletion(
                content='{"action":"capability_lookup","capability_query":"ticket creation"}'
            ),
            ChatCompletion(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="find",
                        name="capability_search",
                        arguments={"action": "find", "query": "ticket"},
                    ),
                ),
            ),
            ChatCompletion(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="create",
                        name="capability_execute",
                        arguments={
                            "skill_id": ticket_tool.capability_id,
                            "input": {"title": "Incident"},
                        },
                    ),
                ),
            ),
        ]
    )
    runtime_profile = replace(
        profile(),
        mcp_servers=(
            RuntimeMcpServerProfile(
                id="mcp_test",
                name="Ticket MCP",
                transport="streamable_http",
                endpoint="https://mcp.example.test",
                arguments=(),
                encrypted_credentials=(),
                tool_policies=(
                    RuntimeMcpToolPolicy(
                        name="create_ticket",
                        description="Create ticket",
                        input_schema=schema,
                        schema_hash=mcp_schema_hash(schema),
                        effect="side_effect",
                        approval="required",
                    ),
                ),
            ),
        ),
    )
    runtime = InProcessAgentRuntime(
        model,
        max_tool_rounds=3,
        timeout_seconds=30,
        mcp_executor=cast(McpExecutor, mcp),
        pending_actions=pending,
    )
    events = CapturingEvents()

    await runtime.execute(replace(request(), profile=runtime_profile), events)

    assert len(model.calls) == 3
    assert len(pending.prepared) == 1
    mcp.execute.assert_not_awaited()
    public = events.items[-2][1]
    assert public["runtime_status"] == "waiting_user_action"
    assert public["action"] == {
        "action_id": "pending_1",
        "action_hash": "sha256:action",
        "version": "v1",
        "choices": ["approve", "reject"],
    }
    assert "create_ticket" not in str(public)
    assert "Incident" not in str(public)


@pytest.mark.asyncio
async def test_approved_mcp_action_executes_once_then_uses_the_final_renderer() -> None:
    schema: dict[str, object] = {
        "type": "object",
        "properties": {"title": {"type": "string"}},
        "required": ["title"],
        "additionalProperties": False,
    }
    ticket_tool = RuntimeMcpTool(
        capability_id="mcp:mcp_test:create_ticket",
        server_id="mcp_test",
        server_name="Ticket MCP",
        tool_name="create_ticket",
        description="Create ticket",
        input_schema=schema,
        read_only=False,
    )
    mcp = SimpleNamespace(
        discover=AsyncMock(return_value=(ticket_tool,)),
        execute=AsyncMock(
            return_value={"status": "succeeded", "result": {"ticket_id": "ticket_1"}}
        ),
    )
    pending = RecordingPendingActions()
    snapshot = create_resume_snapshot(
        [
            ChatMessage(role="system", content="root policy"),
            ChatMessage(role="user", content="Create the incident ticket"),
        ]
    )
    action: dict[str, object] = {
        "version": "v1",
        "action_id": "pending_1",
        "action_hash": "sha256:test",
        "status": "approved",
        "call_id": "call_create",
        "capability_id": ticket_tool.capability_id,
        "arguments": {"title": "Incident"},
        "schema_hash": mcp_schema_hash(schema),
        "resume_messages": list(snapshot),
    }
    runtime_profile = replace(
        profile(),
        mcp_servers=(
            RuntimeMcpServerProfile(
                id="mcp_test",
                name="Ticket MCP",
                transport="streamable_http",
                endpoint="https://mcp.example.test",
                arguments=(),
                encrypted_credentials=(),
                tool_policies=(
                    RuntimeMcpToolPolicy(
                        name="create_ticket",
                        description="Create ticket",
                        input_schema=schema,
                        schema_hash=mcp_schema_hash(schema),
                        effect="side_effect",
                        approval="required",
                    ),
                ),
            ),
        ),
    )
    model = FakeModel([ChatCompletion(content="Ticket ticket_1 was created.")])
    runtime = InProcessAgentRuntime(
        model,
        max_tool_rounds=3,
        timeout_seconds=30,
        mcp_executor=cast(McpExecutor, mcp),
        pending_actions=pending,
    )
    events = CapturingEvents()

    await runtime.execute(
        replace(request(), profile=runtime_profile, pending_tool_action=action),
        events,
    )

    assert pending.executions == 1
    assert len(pending.results) == 1
    mcp.execute.assert_awaited_once()
    assert len(model.calls) == 1
    assert model.calls[0][1] == ()
    assert events.items[-1][1]["runtime_status"] == "completed"


@pytest.mark.asyncio
async def test_interrupted_side_effect_is_not_retried_without_an_idempotent_receipt() -> None:
    model = FakeModel([])
    runtime = InProcessAgentRuntime(model, max_tool_rounds=3, timeout_seconds=30)
    events = CapturingEvents()

    await runtime.execute(
        replace(
            request(),
            pending_tool_action={
                "version": "v1",
                "action_id": "pending_1",
                "action_hash": "sha256:action",
                "status": "executing",
            },
        ),
        events,
    )

    assert model.calls == []
    assert events.items[-1][1]["runtime_status"] == "partial"
    assert events.items[-1][1]["partial_reason"] == "pending_action_execution_uncertain"
