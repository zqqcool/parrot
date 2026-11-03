from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field

import pytest
from _agent_runtime_support import CapturingEvents, FakeModel, request

from app.modules.agent_runtime.contracts import ChatCompletion, ToolCall
from app.modules.agent_runtime.in_process import InProcessAgentRuntime
from app.modules.agent_runtime.model_observation import tool_result_message
from app.modules.agent_runtime.planner import AgentPlanProtocolError


def test_tool_result_message_redacts_and_bounds_model_context() -> None:
    rendered = tool_result_message(
        {
            "status": "ok",
            "token": "secret-token",
            "details": {"authorization": "Bearer another-secret"},
            "payload": "x" * 20_000,
        }
    )

    assert len(rendered) <= 12_000
    assert "secret-token" not in rendered
    assert "another-secret" not in rendered
    assert "[REDACTED]" in rendered
    assert "truncated_for_model" in rendered
    nested = tool_result_message(
        {"status": "ok", "details": {f"field_{index}": "x" * 2_000 for index in range(80)}}
    )
    assert len(nested) <= 12_000
    assert json.loads(nested)["model_context_truncated"] is True


@pytest.mark.asyncio
async def test_invalid_planner_output_fails_closed_instead_of_answering_directly() -> None:
    model = FakeModel([ChatCompletion(content="not-json")], auto_final_response=False)
    runtime = InProcessAgentRuntime(model, max_tool_rounds=2, timeout_seconds=30)

    with pytest.raises(AgentPlanProtocolError, match="valid JSON"):
        await runtime.execute(request(), CapturingEvents())

    assert len(model.calls) == 1


@pytest.mark.asyncio
async def test_planner_accepts_one_json_markdown_fence() -> None:
    model = FakeModel(
        [
            ChatCompletion(content='```json\n{"action":"direct_answer"}\n```'),
            ChatCompletion(content="Done."),
        ],
        auto_final_response=False,
    )
    events = CapturingEvents()
    runtime = InProcessAgentRuntime(model, max_tool_rounds=2, timeout_seconds=30)

    await runtime.execute(request(), events)

    assert any(event_type == "ai.output.completed" for event_type, _ in events.items)
    assert len(model.calls) == 2


@pytest.mark.asyncio
async def test_agent_loop_blocks_repeated_capability_execution() -> None:
    model = FakeModel(
        [
            ChatCompletion(
                content='{"action":"capability_lookup","capability_query":"release notes"}'
            ),
            ChatCompletion(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="call_first",
                        name="capability_execute",
                        arguments={"skill_id": "skill_test", "input": {"query": "release notes"}},
                    ),
                ),
            ),
            ChatCompletion(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="call_repeat",
                        name="capability_execute",
                        arguments={"skill_id": "skill_test", "input": {"query": "release notes"}},
                    ),
                ),
            ),
            ChatCompletion(content="I will not repeat the call."),
        ]
    )
    runtime = InProcessAgentRuntime(
        model,
        max_tool_rounds=3,
        max_finalization_replans=0,
        timeout_seconds=30,
    )

    await runtime.execute(request(), CapturingEvents())

    tool_messages = [
        message.content or "" for message in model.calls[-1][0] if message.role == "tool"
    ]
    assert any("CAPABILITY_EXECUTION_REPEAT_BLOCKED" in message for message in tool_messages)


@dataclass
class _ConcurrentGate:
    starts: int = 0
    both_started: asyncio.Event = field(default_factory=asyncio.Event)

    async def arrive(self) -> None:
        self.starts += 1
        if self.starts == 2:
            self.both_started.set()
        await asyncio.wait_for(self.both_started.wait(), timeout=0.2)


@dataclass
class _GateTimeRuntime:
    gate: _ConcurrentGate

    async def handle(self, arguments: dict[str, object]) -> dict[str, object]:
        del arguments
        await self.gate.arrive()
        return {"status": "ok"}


@dataclass
class _GateMathRuntime:
    gate: _ConcurrentGate

    async def handle(self, arguments: dict[str, object]) -> dict[str, object]:
        del arguments
        await self.gate.arrive()
        return {"status": "ok"}


@pytest.mark.asyncio
async def test_agent_loop_runs_only_pure_builtin_tools_in_parallel() -> None:
    model = FakeModel(
        [
            ChatCompletion(content='{"action":"capability_lookup"}'),
            ChatCompletion(
                content=None,
                tool_calls=(
                    ToolCall(id="call_time", name="time", arguments={"action": "now"}),
                    ToolCall(
                        id="call_math",
                        name="math",
                        arguments={"action": "evaluate", "expression": "1 + 1"},
                    ),
                ),
            ),
            ChatCompletion(content="Done"),
        ]
    )
    gate = _ConcurrentGate()
    runtime = InProcessAgentRuntime(
        model,
        max_tool_rounds=3,
        timeout_seconds=30,
        max_parallel_tool_calls=2,
        time_runtime=_GateTimeRuntime(gate),
        math_runtime=_GateMathRuntime(gate),
    )

    await runtime.execute(request(), CapturingEvents())

    assert gate.starts == 2


@pytest.mark.asyncio
async def test_capability_plan_cannot_conclude_after_only_ranking_candidates() -> None:
    model = FakeModel(
        [
            ChatCompletion(
                content='{"action":"capability_lookup","capability_query":"release notes"}'
            ),
            ChatCompletion(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="call_find",
                        name="capability_search",
                        arguments={"action": "find", "query": "release notes"},
                    ),
                ),
            ),
            ChatCompletion(content="I found enough information."),
        ],
        auto_final_response=False,
    )
    events = CapturingEvents()
    runtime = InProcessAgentRuntime(
        model,
        max_tool_rounds=3,
        max_finalization_replans=0,
        timeout_seconds=30,
    )

    await runtime.execute(request(), events)

    assert events.items[-1][1]["runtime_status"] == "partial"
    assert events.items[-1][1]["partial_reason"] == "capability_observation_required"


@pytest.mark.asyncio
async def test_failed_capability_execution_allows_an_honest_explanation() -> None:
    model = FakeModel(
        [
            ChatCompletion(
                content='{"action":"capability_lookup","capability_query":"release notes"}'
            ),
            ChatCompletion(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="call_execute",
                        name="capability_execute",
                        arguments={"capability_id": "missing_capability"},
                    ),
                ),
            ),
            ChatCompletion(content="The configured capability was unavailable, so I did not act."),
        ],
        auto_final_response=False,
    )
    events = CapturingEvents()
    runtime = InProcessAgentRuntime(
        model,
        max_tool_rounds=3,
        max_finalization_replans=0,
        timeout_seconds=30,
    )

    await runtime.execute(request(), events)

    assert events.items[-1][1]["runtime_status"] == "completed"
    assert events.items[-1][1]["content"] == (
        "The configured capability was unavailable, so I did not act."
    )


@pytest.mark.asyncio
async def test_tool_arguments_are_validated_against_the_published_definition() -> None:
    model = FakeModel(
        [
            ChatCompletion(
                content='{"action":"capability_lookup","capability_query":"release notes"}'
            ),
            ChatCompletion(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="call_invalid",
                        name="capability_search",
                        arguments={
                            "action": "find",
                            "query": "release notes",
                            "unexpected": True,
                        },
                    ),
                ),
            ),
            ChatCompletion(content="I could not validate the capability request."),
        ],
        auto_final_response=False,
    )
    events = CapturingEvents()
    runtime = InProcessAgentRuntime(
        model,
        max_tool_rounds=3,
        max_finalization_replans=0,
        timeout_seconds=30,
    )

    await runtime.execute(request(), events)

    tool_messages = [
        message.content or "" for message in model.calls[-1][0] if message.role == "tool"
    ]
    assert any("TOOL_ARGUMENTS_INVALID" in message for message in tool_messages)
    assert events.items[-1][1]["runtime_status"] == "partial"


@pytest.mark.asyncio
async def test_successful_capability_execution_satisfies_the_completion_gate() -> None:
    model = FakeModel(
        [
            ChatCompletion(
                content='{"action":"capability_lookup","capability_query":"release notes"}'
            ),
            ChatCompletion(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="call_load",
                        name="capability_search",
                        arguments={"action": "load", "skill_id": "skill_test"},
                    ),
                ),
            ),
            ChatCompletion(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="call_execute",
                        name="capability_execute",
                        arguments={"skill_id": "skill_test"},
                    ),
                ),
            ),
            ChatCompletion(content="Verified release guidance."),
        ],
        auto_final_response=False,
    )
    events = CapturingEvents()
    runtime = InProcessAgentRuntime(model, max_tool_rounds=3, timeout_seconds=30)

    await runtime.execute(request(), events)

    assert events.items[-1][1]["runtime_status"] == "completed"
    assert events.items[-1][1]["content"] == "Verified release guidance."
