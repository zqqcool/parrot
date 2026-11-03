from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, replace

import pytest
from _agent_runtime_support import (
    CapturingEvents,
    FakeModel,
    ask_user,
    profile,
    request,
)

from app.core.agent_runtime import RuntimeLlmProfile
from app.modules.agent_runtime.contracts import (
    ChatCompletion,
    ChatCompletionDelta,
    ChatMessage,
    ModelProviderError,
    ModelToolChoice,
    ToolCall,
    ToolDefinition,
)
from app.modules.agent_runtime.in_process import InProcessAgentRuntime
from app.modules.agent_runtime.model_retry import complete_with_retry


@dataclass
class _TransientModel:
    outcomes: list[ChatCompletion | ModelProviderError]
    calls: int = 0

    def validate(self, llm: RuntimeLlmProfile) -> None:
        del llm

    async def complete(
        self,
        llm: RuntimeLlmProfile,
        messages: tuple[ChatMessage, ...],
        tools: tuple[ToolDefinition, ...] = (),
        *,
        tool_choice: ModelToolChoice | None = None,
    ) -> ChatCompletion:
        del llm, messages, tools, tool_choice
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, ModelProviderError):
            raise outcome
        return outcome

    async def stream(
        self,
        llm: RuntimeLlmProfile,
        messages: tuple[ChatMessage, ...],
        tools: tuple[ToolDefinition, ...] = (),
        *,
        tool_choice: ModelToolChoice | None = None,
    ) -> AsyncIterator[ChatCompletionDelta]:
        completion = await self.complete(llm, messages, tools, tool_choice=tool_choice)
        if completion.content:
            yield ChatCompletionDelta(content_delta=completion.content)


@pytest.mark.asyncio
async def test_transient_model_error_is_retried_within_the_runtime_budget() -> None:
    model = _TransientModel(
        [ModelProviderError("temporary", retryable=True), ChatCompletion(content="Recovered")]
    )

    completion = await complete_with_retry(
        model,
        profile().llm,
        (ChatMessage(role="user", content="hello"),),
        (),
        max_retries=1,
    )

    assert completion.content == "Recovered"
    assert model.calls == 2


@pytest.mark.asyncio
async def test_plain_text_is_delivered_without_a_terminal_tool() -> None:
    model = FakeModel(
        [
            ChatCompletion(content='{"action":"direct_answer"}'),
            ChatCompletion(content="No configured source can provide the current release status."),
        ],
        auto_final_response=False,
    )
    runtime = InProcessAgentRuntime(model, max_tool_rounds=3, timeout_seconds=30)
    events = CapturingEvents()

    await runtime.execute(replace(request(), profile=replace(profile(), skills=())), events)

    assert len(model.calls) == 2
    assert events.items[-1][0] == "ai.output.completed"
    assert (
        events.items[-1][1]["content"]
        == "No configured source can provide the current release status."
    )


@pytest.mark.asyncio
async def test_plain_text_that_needs_user_input_becomes_a_waiting_interaction() -> None:
    model = FakeModel(
        [
            ChatCompletion(content='{"action":"direct_answer"}'),
            ask_user("I need you to provide the release identifier first."),
        ],
        auto_final_response=False,
    )
    runtime = InProcessAgentRuntime(
        model,
        max_tool_rounds=3,
        timeout_seconds=30,
        direct_rendering_enabled=False,
    )
    events = CapturingEvents()

    await runtime.execute(replace(request(), profile=replace(profile(), skills=())), events)

    assert events.items[-1][0] == "ai.output.completed"
    assert events.items[-1][1]["runtime_status"] == "waiting_user_input"


@pytest.mark.asyncio
async def test_consecutive_tool_errors_end_with_a_partial_summary() -> None:
    model = FakeModel(
        [
            ChatCompletion(content='{"action":"capability_lookup"}'),
            ChatCompletion(
                content=None,
                tool_calls=(ToolCall(id="unknown", name="unknown_tool", arguments={}),),
            ),
            ChatCompletion(content="The requested tool is unavailable, so the task is incomplete."),
        ]
    )
    runtime = InProcessAgentRuntime(
        model,
        max_tool_rounds=3,
        max_consecutive_tool_errors=1,
        max_control_plane_replans=0,
        timeout_seconds=30,
    )
    events = CapturingEvents()

    await runtime.execute(replace(request(), profile=replace(profile(), skills=())), events)

    assert events.items[-1][0] == "ai.output.completed"
    assert events.items[-1][1]["runtime_status"] == "partial"
    assert events.items[-1][1]["budget_reason"] == "max_consecutive_tool_errors_exceeded"


@pytest.mark.asyncio
async def test_control_plane_failure_replans_once_before_the_next_model_turn() -> None:
    model = FakeModel(
        [
            ChatCompletion(content='{"action":"capability_lookup"}'),
            ChatCompletion(
                content=None,
                tool_calls=(ToolCall(id="missing", name="missing_tool", arguments={}),),
            ),
            ChatCompletion(content='{"action":"direct_answer"}'),
            ChatCompletion(content="The configured capability is unavailable."),
        ]
    )
    runtime = InProcessAgentRuntime(
        model,
        max_tool_rounds=3,
        max_consecutive_tool_errors=1,
        max_control_plane_replans=1,
        timeout_seconds=30,
    )
    events = CapturingEvents()

    await runtime.execute(request(), events)

    plans = [data for event_type, data in events.items if event_type == "ai.agent.plan.created"]
    assert plans == [
        {"action": "capability_lookup", "synthetic": False},
        {"action": "direct_answer", "synthetic": False, "reason": "control_plane_error"},
    ]
    assert events.items[-1][1]["runtime_status"] == "completed"
    assert "Previous control-plane error: TOOL_NOT_AVAILABLE" in (
        model.calls[2][0][0].content or ""
    )
