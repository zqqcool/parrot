from __future__ import annotations

from dataclasses import replace

import pytest
from _agent_runtime_support import CapturingEvents, FakeModel, request

from app.modules.agent_runtime.contracts import ChatCompletion
from app.modules.agent_runtime.in_process import InProcessAgentRuntime


@pytest.mark.asyncio
async def test_root_websocket_streams_thinking_when_enabled() -> None:
    model = FakeModel(
        [
            ChatCompletion(content='{"action":"direct_answer"}'),
            ChatCompletion(
                content="Final answer",
                reasoning_content="Considering the facts",
            ),
        ],
        auto_final_response=False,
    )
    runtime = InProcessAgentRuntime(
        model,
        max_tool_rounds=3,
        timeout_seconds=90,
        direct_rendering_enabled=False,
    )
    events = CapturingEvents()
    runtime_request = request()
    assert runtime_request.profile is not None
    runtime_request = replace(
        runtime_request,
        profile=replace(
            runtime_request.profile,
            llm=replace(runtime_request.profile.llm, thinking_enabled=True),
        ),
    )

    await runtime.execute(runtime_request, events)

    thinking = [item for item in events.items if item[0].startswith("ai.thinking.")]
    assert thinking == [
        (
            "ai.thinking.delta",
            {
                "thinking_id": "thinking_interaction_test_0",
                "delta": "Considering the facts",
                "delta_index": 0,
            },
        ),
        (
            "ai.thinking.completed",
            {
                "thinking_id": "thinking_interaction_test_0",
                "content": "Considering the facts",
            },
        ),
    ]
    assert any(item[0] == "ai.output.delta" for item in events.items)
    assert any(item[0] == "ai.output.completed" for item in events.items)


@pytest.mark.asyncio
async def test_thinking_stays_private_when_disabled() -> None:
    model = FakeModel(
        [
            ChatCompletion(content='{"action":"direct_answer"}'),
            ChatCompletion(
                content="Final answer",
                reasoning_content="private reasoning",
            ),
        ],
        auto_final_response=False,
    )
    runtime = InProcessAgentRuntime(
        model,
        max_tool_rounds=3,
        timeout_seconds=90,
        direct_rendering_enabled=False,
    )
    events = CapturingEvents()

    await runtime.execute(request(), events)

    assert not any(item[0].startswith("ai.thinking.") for item in events.items)
    assert "private reasoning" not in str(
        [data for event_type, data in events.items if event_type.startswith("ai.output.")]
    )
