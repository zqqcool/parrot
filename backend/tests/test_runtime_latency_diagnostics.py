from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from _agent_runtime_support import CapturingEvents, FakeModel, request

from app.modules.agent_runtime.contracts import ChatCompletion, ModelTokenUsage, ToolCall
from app.modules.agent_runtime.diagnostics import RuntimeDiagnostics
from app.modules.agent_runtime.in_process import InProcessAgentRuntime


@pytest.mark.asyncio
async def test_queue_wait_milestone_uses_enqueued_at() -> None:
    model = FakeModel(
        [ChatCompletion(content='{"action":"direct_answer"}'), ChatCompletion(content="Done")],
        auto_final_response=False,
    )
    runtime = InProcessAgentRuntime(
        model,
        max_tool_rounds=2,
        timeout_seconds=30,
        direct_rendering_enabled=False,
    )
    events = CapturingEvents()
    enqueued = datetime.now(UTC) - timedelta(milliseconds=120)
    await runtime.execute(replace(request(), enqueued_at=enqueued), events)

    milestones = [data for trace_type, data in events.traces if trace_type == "runtime.milestone"]
    queue = next(item for item in milestones if item["name"] == "queue_wait")
    assert queue["queue_wait_ms"] >= 100


@pytest.mark.asyncio
async def test_model_turn_completed_records_duration_and_turn() -> None:
    model = FakeModel(
        [
            ChatCompletion(content='{"action":"direct_answer"}'),
            ChatCompletion(
                content=None,
                tool_calls=(ToolCall(id="call_time", name="time", arguments={"action": "now"}),),
            ),
            ChatCompletion(content="It is noon."),
        ],
        auto_final_response=False,
    )
    runtime = InProcessAgentRuntime(
        model, max_tool_rounds=2, timeout_seconds=30, direct_rendering_enabled=False
    )
    events = CapturingEvents()
    await runtime.execute(request(), events)

    turns = [
        data
        for trace_type, data in events.traces
        if trace_type == "runtime.milestone" and data["name"] == "model_turn_completed"
    ]
    assert [item["turn"] for item in turns] == [1, 2]
    assert all(isinstance(item["duration_ms"], float) for item in turns)
    assert turns[0]["tool_call_count"] == 1
    assert turns[1]["content_characters"] > 0


@pytest.mark.asyncio
async def test_tool_result_trace_includes_duration_ms() -> None:
    events = CapturingEvents()
    diagnostics = RuntimeDiagnostics(request(), events)
    await diagnostics.tool_result(
        ToolCall(id="call_1", name="time", arguments={}),
        {"status": "ok"},
        duration_ms=12.5,
    )
    assert events.traces[-1] == (
        "tool.result",
        {
            "tool_call_id": "call_1",
            "name": "time",
            "status": "ok",
            "code": "",
            "duration_ms": 12.5,
        },
    )


@pytest.mark.asyncio
async def test_model_response_trace_includes_usage_when_present() -> None:
    events = CapturingEvents()
    diagnostics = RuntimeDiagnostics(request(), events)
    await diagnostics.model_response(
        "agent_loop",
        ChatCompletion(
            content="hello",
            finish_reason="stop",
            usage=ModelTokenUsage(
                prompt_tokens=10,
                completion_tokens=2,
                total_tokens=12,
                cached_tokens=8,
            ),
        ),
    )
    assert events.traces[-1] == (
        "model.response",
        {
            "phase": "agent_loop",
            "finish_reason": "stop",
            "content_characters": 5,
            "tool_call_names": [],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 2,
                "total_tokens": 12,
                "cached_tokens": 8,
            },
        },
    )
