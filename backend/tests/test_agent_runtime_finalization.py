from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import replace

import pytest
from _agent_runtime_support import CapturingEvents, FakeModel, ask_user, request

from app.core.agent_runtime import RuntimeLlmProfile
from app.modules.agent_runtime.contracts import (
    ChatCompletion,
    ChatCompletionDelta,
    ChatMessage,
    ModelProviderError,
    ModelToolChoice,
    ToolCall,
    ToolCallDelta,
    ToolDefinition,
)
from app.modules.agent_runtime.final_renderer import FinalRenderProviderError
from app.modules.agent_runtime.final_response import (
    FinalResponseProtocolError,
    terminal_intent_from,
)
from app.modules.agent_runtime.in_process import InProcessAgentRuntime
from app.modules.agent_runtime.taskboard import create_task_board
from app.modules.interactions.runtime import RuntimeControlState


class ChunkedFinalModel(FakeModel):
    async def stream(
        self,
        llm: RuntimeLlmProfile,
        messages: tuple[ChatMessage, ...],
        tools: tuple[ToolDefinition, ...] = (),
        *,
        tool_choice: ModelToolChoice | None = None,
    ) -> AsyncIterator[ChatCompletionDelta]:
        if tools:
            async for delta in super().stream(
                llm,
                messages,
                tools,
                tool_choice=tool_choice,
            ):
                yield delta
            return
        self.calls.append((messages, tools))
        self.tool_choices.append(tool_choice)
        yield ChatCompletionDelta(content_delta="Hel")
        yield ChatCompletionDelta(content_delta="lo")


class ChunkedCandidateModel(FakeModel):
    events: CapturingEvents | None = None

    async def stream(
        self,
        llm: RuntimeLlmProfile,
        messages: tuple[ChatMessage, ...],
        tools: tuple[ToolDefinition, ...] = (),
        *,
        tool_choice: ModelToolChoice | None = None,
    ) -> AsyncIterator[ChatCompletionDelta]:
        if not tools:
            async for delta in super().stream(
                llm,
                messages,
                tools,
                tool_choice=tool_choice,
            ):
                yield delta
            return
        self.calls.append((messages, tools))
        self.tool_choices.append(tool_choice)
        completion = self.responses.pop(0)
        if completion.content:
            yield ChatCompletionDelta(content_delta="Hel")
            if self.events is not None:
                assert any(
                    event_type == "ai.output.delta" for event_type, _ in self.events.items
                )
            yield ChatCompletionDelta(content_delta="lo")
        for index, call in enumerate(completion.tool_calls):
            yield ChatCompletionDelta(
                tool_call_deltas=(
                    ToolCallDelta(
                        index=index,
                        id=call.id,
                        name=call.name,
                        arguments_delta="{}",
                    ),
                )
            )
            if completion.content and self.events is not None:
                assert any(
                    event_type == "ai.output.reset" for event_type, _ in self.events.items
                )


class RecoveringFinalModel:
    def __init__(self) -> None:
        self.agent_turns = 0
        self.renderer_attempts = 0

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
        return ChatCompletion(content='{"action":"direct_answer"}')

    async def stream(
        self,
        llm: RuntimeLlmProfile,
        messages: tuple[ChatMessage, ...],
        tools: tuple[ToolDefinition, ...] = (),
        *,
        tool_choice: ModelToolChoice | None = None,
    ) -> AsyncIterator[ChatCompletionDelta]:
        del llm, messages, tool_choice
        if tools:
            self.agent_turns += 1
            yield ChatCompletionDelta(
                tool_call_deltas=(
                    ToolCallDelta(
                        index=0,
                        id="final",
                        name="final_response",
                        arguments_delta="{}",
                    ),
                )
            )
            return
        self.renderer_attempts += 1
        if self.renderer_attempts == 1:
            yield ChatCompletionDelta(content_delta="Hel")
            raise ModelProviderError("connection reset", retryable=True)
        yield ChatCompletionDelta(content_delta="Hello")


class SteerDuringFinalRenderReader:
    def __init__(self) -> None:
        self.calls = 0

    async def consume(self, request: object) -> RuntimeControlState:
        del request
        self.calls += 1
        if self.calls == 4:
            return RuntimeControlState(steering_messages=("Use the current production release.",))
        return RuntimeControlState()


class FailingCandidateEvents(CapturingEvents):
    def __init__(self) -> None:
        super().__init__()
        self._completed_count = 0

    async def append(
        self,
        *,
        tenant_id: str,
        interaction_id: str,
        request_id: str,
        event_type: str,
        data: dict[str, object],
        terminal_status: str | None = None,
        runtime_event_sequence: int | None = None,
        lease_owner: str | None = None,
    ) -> object:
        if event_type == "ai.output.completed":
            self._completed_count += 1
            if self._completed_count == 1:
                raise RuntimeError("event delivery interrupted")
        return await super().append(
            tenant_id=tenant_id,
            interaction_id=interaction_id,
            request_id=request_id,
            event_type=event_type,
            data=data,
            terminal_status=terminal_status,
            runtime_event_sequence=runtime_event_sequence,
            lease_owner=lease_owner,
        )


@pytest.mark.asyncio
async def test_agent_loop_live_streams_plain_text_during_provider_sse() -> None:
    model = ChunkedCandidateModel(
        [
            ChatCompletion(content='{"action":"direct_answer"}'),
            ChatCompletion(content="Hello"),
            ChatCompletion(content="This repair must not be requested."),
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
    model.events = events

    await runtime.execute(request(), events)

    assert [item for item in events.items if item[0].startswith("ai.output.")] == [
        (
            "ai.output.delta",
            {"output_id": "output_interaction_test", "delta": "Hel", "delta_index": 0},
        ),
        (
            "ai.output.delta",
            {"output_id": "output_interaction_test", "delta": "lo", "delta_index": 1},
        ),
        (
            "ai.output.completed",
            {
                "output_id": "output_interaction_test",
                "content": "Hello",
                "runtime_status": "completed",
            },
        ),
    ]
    assert len(model.calls) == 2


@pytest.mark.asyncio
async def test_live_delivery_recovers_without_another_model_request() -> None:
    model = ChunkedCandidateModel(
        [
            ChatCompletion(content='{"action":"direct_answer"}'),
            ChatCompletion(content="Hello"),
        ],
        auto_final_response=False,
    )
    runtime = InProcessAgentRuntime(
        model,
        max_tool_rounds=3,
        timeout_seconds=90,
        direct_rendering_enabled=False,
    )
    interrupted_events = FailingCandidateEvents()

    with pytest.raises(RuntimeError, match="event delivery interrupted"):
        await runtime.execute(request(), interrupted_events)

    recovered_events = CapturingEvents()
    await runtime.execute(request(), recovered_events)

    assert len(model.calls) == 2
    assert [item for item in recovered_events.items if item[0].startswith("ai.output.")] == [
        (
            "ai.output.reset",
            {
                "output_id": "output_interaction_test",
                "reason": "candidate_output_recovered",
            },
        ),
        (
            "ai.output.delta",
            {"output_id": "output_interaction_test", "delta": "Hello", "delta_index": 0},
        ),
        (
            "ai.output.completed",
            {
                "output_id": "output_interaction_test",
                "content": "Hello",
                "runtime_status": "completed",
            },
        ),
    ]


@pytest.mark.asyncio
async def test_capability_plan_does_not_publish_an_unobserved_candidate() -> None:
    model = FakeModel(
        [
            ChatCompletion(
                content='{"action":"capability_lookup","capability_query":"release status"}'
            ),
            ChatCompletion(content="The release is complete."),
            ChatCompletion(content="The release is complete."),
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

    assert [item for item in events.items if item[0].startswith("ai.output.")] == [
        (
            "ai.output.completed",
            {
                "output_id": "output_interaction_test",
                "content": "暂时未获得完成此请求所需的信息，请稍后重试。",
                "runtime_status": "partial",
                    "partial_reason": "capability_observation_required",
            },
        )
    ]


@pytest.mark.asyncio
async def test_capability_plan_rejects_a_premature_final_response_signal() -> None:
    premature = ChatCompletion(
        content=None,
        tool_calls=(ToolCall(id="call_final", name="final_response", arguments={}),),
    )
    model = FakeModel(
        [
            ChatCompletion(
                content='{"action":"capability_lookup","capability_query":"release status"}'
            ),
            premature,
            premature,
        ],
        auto_final_response=False,
    )
    runtime = InProcessAgentRuntime(model, max_tool_rounds=3, timeout_seconds=90)
    events = CapturingEvents()

    await runtime.execute(request(), events)

    assert len(model.calls) == 3
    assert [item for item in events.items if item[0].startswith("ai.output.")] == [
        (
            "ai.output.completed",
            {
                "output_id": "output_interaction_test",
                "content": "暂时未获得完成此请求所需的信息，请稍后重试。",
                "runtime_status": "partial",
                    "partial_reason": "capability_observation_required",
            },
        )
    ]


@pytest.mark.asyncio
async def test_final_renderer_publishes_provider_deltas_without_rechunking() -> None:
    model = ChunkedFinalModel(
        [ChatCompletion(content='{"action":"direct_answer"}')],
        auto_final_response=False,
    )
    events = CapturingEvents()
    runtime = InProcessAgentRuntime(model, max_tool_rounds=3, timeout_seconds=90)

    await runtime.execute(request(), events)

    output_events = [item for item in events.items if item[0].startswith("ai.output.")]
    assert output_events == [
        (
            "ai.output.delta",
            {"output_id": "output_interaction_test", "delta": "Hel", "delta_index": 0},
        ),
        (
            "ai.output.delta",
            {"output_id": "output_interaction_test", "delta": "lo", "delta_index": 1},
        ),
        (
            "ai.output.completed",
            {
                "output_id": "output_interaction_test",
                "content": "Hello",
                "runtime_status": "completed",
            },
        ),
    ]
    milestones = [data for trace_type, data in events.traces if trace_type == "runtime.milestone"]
    assert [item["name"] for item in milestones] == [
        "public_first_delta",
        "run_completed",
    ]
    assert milestones[0]["phase"] == "final_renderer"
    provider_elapsed = milestones[0]["provider_elapsed_ms"]
    public_elapsed = milestones[0]["elapsed_ms"]
    assert isinstance(provider_elapsed, float)
    assert isinstance(public_elapsed, float)
    assert provider_elapsed <= public_elapsed


@pytest.mark.asyncio
async def test_final_renderer_recovers_without_rerunning_the_agent_tool_loop() -> None:
    model = RecoveringFinalModel()
    events = CapturingEvents()
    runtime = InProcessAgentRuntime(model, max_tool_rounds=3, timeout_seconds=90)

    with pytest.raises(FinalRenderProviderError):
        await runtime.execute(request(), events)
    await runtime.execute(request(), events)

    assert model.agent_turns == 0
    assert model.renderer_attempts == 2
    output_events = [item for item in events.items if item[0].startswith("ai.output.")]
    assert output_events == [
        (
            "ai.output.delta",
            {"output_id": "output_interaction_test", "delta": "Hel", "delta_index": 0},
        ),
        (
            "ai.output.reset",
            {
                "output_id": "output_interaction_test",
                "reason": "final_render_recovered",
            },
        ),
        (
            "ai.output.delta",
            {"output_id": "output_interaction_test", "delta": "Hello", "delta_index": 0},
        ),
        (
            "ai.output.completed",
            {
                "output_id": "output_interaction_test",
                "content": "Hello",
                "runtime_status": "completed",
            },
        ),
    ]


@pytest.mark.asyncio
async def test_final_renderer_restarts_for_steering_without_losing_the_message() -> None:
    model = ChunkedFinalModel(
        [ChatCompletion(content='{"action":"direct_answer"}')],
        auto_final_response=False,
    )
    events = CapturingEvents()
    runtime = InProcessAgentRuntime(model, max_tool_rounds=3, timeout_seconds=90)

    await runtime.execute(
        replace(request(), control_reader=SteerDuringFinalRenderReader()),
        events,
    )

    output_events = [item for item in events.items if item[0].startswith("ai.output.")]
    assert [event_type for event_type, _ in output_events] == [
        "ai.output.delta",
        "ai.output.reset",
        "ai.output.delta",
        "ai.output.delta",
        "ai.output.completed",
    ]
    final_requests = [messages for messages, tools in model.calls if not tools]
    assert any(
        message.role == "user" and message.content == "Use the current production release."
        for message in final_requests[-1]
    )


@pytest.mark.asyncio
async def test_tool_backed_plain_text_is_delivered_without_a_rewrite_turn() -> None:
    model = FakeModel(
        [
            ChatCompletion(content='{"action":"agent_loop"}'),
            ChatCompletion(
                content=None,
                tool_calls=(ToolCall(id="call_time", name="time", arguments={"action": "now"}),),
            ),
            ChatCompletion(content="Hello from the tool-backed loop."),
            ChatCompletion(content="This rewrite must not run."),
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

    assert [item for item in events.items if item[0].startswith("ai.output.")] == [
        (
            "ai.output.delta",
            {
                "output_id": "output_interaction_test",
                "delta": "Hello from the tool-backed loop.",
                "delta_index": 0,
            },
        ),
        (
            "ai.output.completed",
            {
                "output_id": "output_interaction_test",
                "content": "Hello from the tool-backed loop.",
                "runtime_status": "completed",
            },
        ),
    ]
    assert len(model.calls) == 3
    assert model.calls[-1][1]  # tool-backed plain text must not enter tools=[] renderer
    assert events.items[-1][1]["content"] == "Hello from the tool-backed loop."


@pytest.mark.asyncio
async def test_signal_only_final_response_enters_final_renderer_for_live_deltas() -> None:
    model = ChunkedFinalModel(
        [
            ChatCompletion(content='{"action":"agent_loop"}'),
            ChatCompletion(
                content=None,
                tool_calls=(ToolCall(id="call_time", name="time", arguments={"action": "now"}),),
            ),
            ChatCompletion(
                content=None,
                tool_calls=(ToolCall(id="call_final", name="final_response", arguments={}),),
            ),
            ChatCompletion(content="Hello"),
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

    assert [item for item in events.items if item[0].startswith("ai.output.")] == [
        (
            "ai.output.delta",
            {"output_id": "output_interaction_test", "delta": "Hel", "delta_index": 0},
        ),
        (
            "ai.output.delta",
            {"output_id": "output_interaction_test", "delta": "lo", "delta_index": 1},
        ),
        (
            "ai.output.completed",
            {
                "output_id": "output_interaction_test",
                "content": "Hello",
                "runtime_status": "completed",
            },
        ),
    ]
    assert model.calls[-1][1] == ()


@pytest.mark.asyncio
async def test_agent_loop_delivers_plain_text_without_a_final_response_tool() -> None:
    model = FakeModel(
        [
            ChatCompletion(content='{"action":"direct_answer"}'),
            ChatCompletion(content="First unstructured draft"),
            ChatCompletion(content="Second unstructured draft"),
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

    assert events.items[-1] == (
        "ai.output.completed",
        {
            "output_id": "output_interaction_test",
            "content": "First unstructured draft",
            "runtime_status": "completed",
        },
    )


@pytest.mark.asyncio
async def test_agent_loop_uses_final_response_status_to_wait_for_the_user() -> None:
    model = FakeModel(
        [
            ChatCompletion(content='{"action":"direct_answer"}'),
            ask_user("Which release should I use?"),
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

    assert events.items[-1] == (
        "ai.output.completed",
        {
            "output_id": "output_interaction_test",
            "content": "Which release should I use?",
            "runtime_status": "waiting_user_input",
        },
    )


def test_final_response_rejects_a_mixed_tool_turn() -> None:
    completion = ChatCompletion(
        content=None,
        tool_calls=(
            ToolCall(
                id="final",
                name="final_response",
                arguments={},
            ),
            ToolCall(id="time", name="time", arguments={"action": "now"}),
        ),
    )

    with pytest.raises(FinalResponseProtocolError):
        terminal_intent_from(completion)


@pytest.mark.asyncio
async def test_completed_parent_taskboard_uses_the_direct_final_renderer() -> None:
    user_text = "Research release notes then draft them"
    board = create_task_board(
        {
            "tasks": [
                {
                    "id": "research",
                    "objective": "Research release notes.",
                    "source_role": "latest_user_request",
                    "source_quote": user_text,
                    "source_span": {"start": 0, "end": len(user_text)},
                },
                {
                    "id": "draft",
                    "objective": "Draft release notes.",
                    "source_role": "latest_user_request",
                    "source_quote": user_text,
                    "source_span": {"start": 0, "end": len(user_text)},
                },
            ]
        },
        user_text,
        depth=0,
    )
    board.settle("research", "completed", {"summary": "research result"})
    board.settle("draft", "completed", {"summary": "draft result"})
    model = FakeModel([ChatCompletion(content="Combined result")], auto_final_response=False)
    runtime = InProcessAgentRuntime(model, max_tool_rounds=3, timeout_seconds=90)
    events = CapturingEvents()

    await runtime.execute(replace(request(), text=user_text, task_board=board.to_dict()), events)

    assert len(model.calls) == 1
    assert model.calls[0][1] == ()
    assert any(
        item.role == "user" and "taskboard_context" in (item.content or "")
        for item in model.calls[0][0]
    )
