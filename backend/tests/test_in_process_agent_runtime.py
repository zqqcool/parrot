from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest
from _agent_runtime_support import (
    CancelReader,
    CapturingEvents,
    FakeConversationHistory,
    FakeMemoryRuntime,
    FakeModel,
    FakeScheduleRuntime,
    FakeSubagentDispatcher,
    ask_user,
    profile,
    request,
)

from app.core.agent_runtime import RuntimeSkillProfile
from app.modules.agent_runtime.capabilities import CapabilitySession
from app.modules.agent_runtime.contracts import ChatCompletion, ToolCall
from app.modules.agent_runtime.in_process import InProcessAgentRuntime
from app.modules.interactions.runtime import RuntimeControlState


class SteeringReader:
    def __init__(self, message: str) -> None:
        self.message = message

    async def consume(self, request: object) -> RuntimeControlState:
        del request
        message, self.message = self.message, ""
        return RuntimeControlState(steering_messages=(message,) if message else ())


@pytest.mark.asyncio
async def test_agent_loop_searches_loads_then_uses_only_bound_instruction_skill() -> None:
    model = FakeModel(
        [
            ChatCompletion(content='{"action":"capability_lookup","capability_query":"release"}'),
            ChatCompletion(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="call_find",
                        name="capability_search",
                        arguments={"action": "find", "query": "release"},
                    ),
                ),
            ),
            ChatCompletion(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="call_load",
                        name="capability_search",
                        arguments={
                            "action": "load",
                            "capability_id": "skill_test",
                            "role": "primary",
                        },
                    ),
                ),
            ),
            ChatCompletion(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="call_execute",
                        name="capability_execute",
                        arguments={"capability_id": "skill_test"},
                    ),
                ),
            ),
            ChatCompletion(content="Release notes are ready."),
        ]
    )
    runtime = InProcessAgentRuntime(model, max_tool_rounds=4, timeout_seconds=90)
    events = CapturingEvents()

    await runtime.execute(request(), events)

    assert [event_type for event_type, _ in events.items] == [
        "ai.input.processed",
        "ai.agent.plan.created",
        "ai.tool.started",
        "ai.tool.completed",
        "ai.tool.started",
        "ai.tool.completed",
        "ai.tool.started",
        "ai.tool.completed",
        "ai.output.delta",
        "ai.output.completed",
    ]
    assert [tool.name for tool in model.calls[1][1]] == [
        "memory",
        "todo",
        "time",
        "math",
        "capability_search",
        "capability_execute",
        "schedule",
        "ask_user",
    ]
    tool_messages = [message for message in model.calls[-1][0] if message.role == "tool"]
    assert "instruction_ready" in (tool_messages[-1].content or "")


@pytest.mark.asyncio
async def test_agent_loop_persists_metadata_only_diagnostics() -> None:
    model = FakeModel(
        [
            ChatCompletion(content='{"action":"capability_lookup"}'),
            ChatCompletion(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="call_find",
                        name="capability_search",
                        arguments={"action": "find", "token": "private-value"},
                    ),
                ),
            ),
            ChatCompletion(content="Release notes are ready."),
        ]
    )
    events = CapturingEvents()
    runtime = InProcessAgentRuntime(
        model,
        max_tool_rounds=3,
        max_finalization_replans=0,
        timeout_seconds=90,
    )

    await runtime.execute(request(), events)

    trace_types = [trace_type for trace_type, _ in events.traces]
    assert trace_types == [
        "model.request",
        "model.response",
        "model.request",
        "model.response",
        "runtime.milestone",
        "tool.call",
        "tool.result",
        "model.request",
        "runtime.milestone",
        "model.response",
        "runtime.milestone",
        "completion.decision",
    ]
    assert events.traces[4][1]["name"] == "model_turn_completed"
    assert events.traces[8][1]["name"] == "provider_first_content_delta"
    assert events.traces[10][1]["name"] == "model_turn_completed"
    planner = events.traces[0][1]
    assert planner["phase"] == "planner"
    assert isinstance(planner["message_count"], int)
    assert planner["message_count"] > 0
    assert "messages" not in planner
    assert "tools" not in planner
    responses = [data for trace_type, data in events.traces if trace_type == "model.response"]
    assert responses[0]["phase"] == "planner"
    assert isinstance(responses[0]["content_characters"], int)
    assert responses[0]["content_characters"] > 0
    assert "response_snapshot" not in responses[0]
    assert responses[1]["tool_call_names"] == ["capability_search"]
    assert "response_snapshot" not in responses[1]
    tool_call = events.traces[5][1]
    assert tool_call == {
        "tool_call_id": "call_find",
        "name": "capability_search",
        "argument_count": 2,
    }
    result = events.traces[6][1]
    assert result["tool_call_id"] == "call_find"
    assert result["name"] == "capability_search"
    assert result["status"] == "rejected"
    assert result["code"] == "TOOL_ARGUMENTS_INVALID"
    assert isinstance(result["duration_ms"], float)
    assert events.traces[-1][1] == {
        "decision": "partial",
        "reason": "capability_observation_required",
        "observation_count": 1,
        "observation_kinds": {
            "control": 1,
            "instruction": 0,
            "read": 0,
            "action": 0,
            "subagent": 0,
            "failure": 0,
        },
    }
    milestone = events.traces[8][1]
    assert milestone["name"] == "provider_first_content_delta"
    assert milestone["phase"] == "agent_loop"
    assert isinstance(milestone["elapsed_ms"], float)
    assert "private-value" not in str(milestone)
    assert "private-value" not in str(events.traces)
    assert "release-notes" not in str(events.traces)
    assert all(event_type != "model.request" for event_type, _ in events.items)


@pytest.mark.asyncio
async def test_agent_loop_captures_provider_ready_prompt_when_explicitly_enabled() -> None:
    model = FakeModel(
        [
            ChatCompletion(content='{"action":"capability_lookup"}'),
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
            ChatCompletion(content="Release notes are ready."),
        ]
    )
    events = CapturingEvents()
    runtime = InProcessAgentRuntime(
        model,
        max_tool_rounds=3,
        max_finalization_replans=0,
        timeout_seconds=90,
        capture_prompts=True,
    )

    await runtime.execute(request(), events)

    requests = [data for trace_type, data in events.traces if trace_type == "model.request"]
    raw_snapshot = requests[0]["request_snapshot"]
    assert isinstance(raw_snapshot, dict)
    snapshot = cast(dict[str, object], raw_snapshot)
    assert snapshot["format"] == "openai-compatible.chat-completions.v1"
    assert snapshot["tools"] == []
    assert "用户最新请求" in str(snapshot["messages"])
    assert "Prepare release notes" in str(snapshot["messages"])
    assert "tool_calls" in str(requests)
    assert requests[1]["tool_choice"] is None
    assert "tool_choice" not in cast(dict[str, object], requests[1]["request_snapshot"])
    responses = [data for trace_type, data in events.traces if trace_type == "model.response"]
    final_snapshot = cast(dict[str, object], responses[-1]["response_snapshot"])
    assert final_snapshot["content"] == "Release notes are ready."
    assert final_snapshot["tool_calls"] == []


@pytest.mark.asyncio
async def test_knowledge_agent_can_answer_without_forced_capability_discovery() -> None:
    model = FakeModel(
        [ChatCompletion(content="Release notes are ready.")],
        auto_final_response=False,
    )
    runtime = InProcessAgentRuntime(
        model,
        max_tool_rounds=4,
        timeout_seconds=90,
    )
    events = CapturingEvents()
    knowledge_profile = replace(profile(), agent_type_key="knowledge")

    await runtime.execute(replace(request(), profile=knowledge_profile), events)

    plan = next(data for event_type, data in events.items if event_type == "ai.agent.plan.created")
    assert plan == {"action": "agent_loop", "synthetic": True}
    assert {tool.name for tool in model.calls[0][1]} >= {
        "knowledge_search",
        "capability_search",
        "capability_execute",
    }
    assert not any(
        message.role == "system" and "使用 action=find 且 query 为空" in (message.content or "")
        for message in model.calls[0][0]
    )


@pytest.mark.asyncio
async def test_agent_loop_applies_the_persisted_agent_system_prompt() -> None:
    model = FakeModel(
        [ChatCompletion(content='{"action":"direct_answer"}'), ChatCompletion(content="Done")]
    )
    runtime = InProcessAgentRuntime(model, max_tool_rounds=2, timeout_seconds=90)
    prompt = "Use concise Chinese headings and do not invent operational results."

    await runtime.execute(
        replace(request(), profile=replace(profile(), system_prompt=prompt)), CapturingEvents()
    )

    assert prompt in (model.calls[0][0][0].content or "")
    assert any(
        item.role == "system"
        and "Agent 策略仅补充回答范围、风格和业务术语" in (item.content or "")
        and prompt in (item.content or "")
        for item in model.calls[1][0]
    )


@pytest.mark.asyncio
async def test_agent_loop_consumes_durable_cancel_before_model_execution() -> None:
    model = FakeModel([])
    runtime = InProcessAgentRuntime(model, max_tool_rounds=4, timeout_seconds=90)
    events = CapturingEvents()
    controlled_request = replace(request(), control_reader=CancelReader())

    await runtime.execute(controlled_request, events)

    assert model.calls == []
    assert events.items == [
        (
            "ai.output.cancelled",
            {"finish_reason": "cancelled", "output_id": "output_interaction_test"},
        )
    ]


@pytest.mark.asyncio
async def test_planner_clarification_is_delegated_to_agent_loop() -> None:
    model = FakeModel(
        [
            ChatCompletion(
                content=('{"action":"clarify","clarifying_question":"Which release should I use?"}')
            ),
            ask_user("Which release should I use?"),
        ]
    )
    runtime = InProcessAgentRuntime(model, max_tool_rounds=3, timeout_seconds=90)
    events = CapturingEvents()

    await runtime.execute(request(), events)

    assert [event_type for event_type, _ in events.items] == [
        "ai.input.processed",
        "ai.agent.plan.created",
        "ai.output.completed",
    ]
    assert events.items[1][1]["action"] == "agent_loop"
    assert events.items[-1][1]["runtime_status"] == "waiting_user_input"
    assert len(model.calls) == 2
    assert model.calls[0][1] == ()
    assert "规划阶段不得向用户提问或请求澄清" in (model.calls[0][0][0].content or "")
    assert "ask_user" in {tool.name for tool in model.calls[1][1]}


@pytest.mark.asyncio
async def test_noninteractive_entry_does_not_wait_for_planner_clarification() -> None:
    model = FakeModel(
        [
            ChatCompletion(content=('{"action":"clarify","clarifying_question":"Which release?"}')),
            ChatCompletion(content="The schedule lacks a release identifier."),
        ]
    )
    runtime = InProcessAgentRuntime(model, max_tool_rounds=3, timeout_seconds=90)
    events = CapturingEvents()

    await runtime.execute(replace(request(), entry_type="schedule"), events)

    assert all(data.get("runtime_status") != "waiting_user_input" for _, data in events.items)
    assert events.items[-1][1]["runtime_status"] == "completed"
    assert events.items[-1][1]["content"] == "The schedule lacks a release identifier."


@pytest.mark.asyncio
async def test_agent_loop_replans_a_resumed_clarification_with_its_context() -> None:
    model = FakeModel(
        [ChatCompletion(content='{"action":"direct_answer"}'), ChatCompletion(content="Resolved")]
    )
    runtime = InProcessAgentRuntime(model, max_tool_rounds=3, timeout_seconds=90)
    resumed = replace(
        request(),
        control_reader=SteeringReader("Use the production release."),
        resume_assistant_message="Which release should I use?",
        control_after_sequence=7,
    )

    await runtime.execute(resumed, CapturingEvents())

    planner_prompt = model.calls[0][0][0].content or ""
    assert "用户最初请求：\nPrepare release notes" in planner_prompt
    assert "助手此前的追问：\nWhich release should I use?" in planner_prompt
    assert "用户最新补充：\nUse the production release." in planner_prompt
    turn = model.calls[1][0]
    assert "本轮为无工具作答" in (turn[0].content or "")
    assert [(item.role, item.content) for item in turn if item.role in {"user", "assistant"}][
        -3:
    ] == [
        ("user", "Prepare release notes"),
        ("assistant", "Which release should I use?"),
        ("user", "Use the production release."),
    ]


@pytest.mark.asyncio
async def test_resumed_turn_uses_a_distinct_persisted_output_id() -> None:
    model = FakeModel(
        [ChatCompletion(content='{"action":"direct_answer"}'), ChatCompletion(content="Resolved")]
    )
    runtime = InProcessAgentRuntime(model, max_tool_rounds=3, timeout_seconds=90)
    events = CapturingEvents()

    await runtime.execute(
        replace(request(), output_id="output_turn_two", profile=replace(profile(), skills=())),
        events,
    )

    output_events = [
        data for event_type, data in events.items if event_type.startswith("ai.output.")
    ]
    assert {data["output_id"] for data in output_events} == {"output_turn_two"}


@pytest.mark.asyncio
async def test_agent_loop_injects_memory_as_reference_data_and_executes_memory_tool() -> None:
    model = FakeModel(
        [
            ChatCompletion(content='{"action":"capability_lookup"}'),
            ChatCompletion(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="call_memory",
                        name="memory",
                        arguments={"action": "search", "query": "preference"},
                    ),
                ),
            ),
            ChatCompletion(content="I found the saved preference."),
        ]
    )
    memory = FakeMemoryRuntime("<memory-context>reference only</memory-context>")
    runtime = InProcessAgentRuntime(
        model,
        max_tool_rounds=3,
        timeout_seconds=90,
        memory_runtime=memory,
    )

    await runtime.execute(request(), CapturingEvents())

    assert memory.contexts[0].agent_id == "agent_test"
    assert memory.calls == [{"action": "search", "query": "preference"}]
    memory_reference = model.calls[1][0][1]
    assert memory_reference.role == "user"
    assert (memory_reference.content or "").count("<memory_context>") == 1
    assert "&lt;memory-context&gt;" not in (memory_reference.content or "")
    assert "reference only" in (memory_reference.content or "")
    assert '"status": "ok"' in (model.calls[2][0][-1].content or "")


@pytest.mark.asyncio
async def test_agent_loop_can_dispatch_once_while_gathering_capability_evidence() -> None:
    model = FakeModel(
        [
            ChatCompletion(content='{"action":"capability_lookup"}'),
            ChatCompletion(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="call_delegate",
                        name="subagent_dispatch",
                        arguments={
                            "tasks": [
                                {
                                    "objective": "Research release notes",
                                    "source_role": "latest_user_request",
                                    "source_quote": "Prepare release notes",
                                    "source_span": {"start": 0, "end": 21},
                                },
                                {
                                    "objective": "Review release notes",
                                    "source_role": "latest_user_request",
                                    "source_quote": "Prepare release notes",
                                    "source_span": {"start": 0, "end": 21},
                                },
                            ]
                        },
                    ),
                ),
            ),
        ]
    )
    dispatcher = FakeSubagentDispatcher()
    runtime = InProcessAgentRuntime(
        model,
        max_tool_rounds=3,
        timeout_seconds=90,
        subagent_dispatcher=dispatcher,
    )

    await runtime.execute(request(), CapturingEvents())

    assert len(dispatcher.calls) == 1
    assert dispatcher.sources == ["agent_loop"]
    assert dispatcher.dispatch_call_ids == ["call_delegate"]
    assert dispatcher.resume_messages[0]
    assert all(message.reasoning_content is None for message in dispatcher.resume_messages[0])
    assert len(model.calls) == 2


@pytest.mark.asyncio
async def test_agent_loop_waits_after_durable_subagent_dispatch() -> None:
    model = FakeModel(
        [
            ChatCompletion(
                content=(
                    '{"action":"subagent_dispatch","tasks":['
                    '{"id":"research","objective":"Research release notes",'
                    '"source_role":"latest_user_request",'
                    '"source_quote":"Prepare release notes","source_span":{"start":0,"end":21}},'
                    '{"id":"draft","objective":"Draft release notes",'
                    '"source_role":"latest_user_request",'
                    '"source_quote":"Prepare release notes","source_span":{"start":0,"end":21}}]}'
                )
            ),
        ]
    )
    dispatcher = FakeSubagentDispatcher()
    runtime = InProcessAgentRuntime(
        model,
        max_tool_rounds=3,
        timeout_seconds=90,
        subagent_dispatcher=dispatcher,
    )
    events = CapturingEvents()
    await runtime.execute(request(), events)

    assert len(dispatcher.calls) == 1
    assert len(cast(list[object], dispatcher.calls[0]["tasks"])) == 2
    assert len(model.calls) == 1
    assert "ai.output.completed" not in [event_type for event_type, _ in events.items]


@pytest.mark.asyncio
async def test_agent_loop_uses_schedule_only_for_root_user_interactions() -> None:
    model = FakeModel(
        [
            ChatCompletion(content='{"action":"capability_lookup"}'),
            ChatCompletion(
                content=None,
                tool_calls=(
                    ToolCall(id="call_schedule", name="schedule", arguments={"action": "list"}),
                ),
            ),
            ChatCompletion(content="Your schedules are listed."),
        ]
    )
    schedules = FakeScheduleRuntime()
    runtime = InProcessAgentRuntime(
        model,
        max_tool_rounds=3,
        timeout_seconds=90,
        schedule_runtime=schedules,
    )

    await runtime.execute(request(), CapturingEvents())

    assert schedules.calls == [{"action": "list"}]
    assert schedules.contexts[0].actor_id == "visitor_test"
    assert "schedule" in [tool.name for tool in model.calls[1][1]]


@pytest.mark.asyncio
async def test_agent_loop_injects_same_conversation_history_as_native_roles() -> None:
    model = FakeModel(
        [ChatCompletion(content='{"action":"direct_answer"}'), ChatCompletion(content="Done")]
    )
    history = FakeConversationHistory()
    runtime = InProcessAgentRuntime(
        model,
        max_tool_rounds=2,
        timeout_seconds=90,
        conversation_history=history,
    )

    await runtime.execute(
        replace(request(), conversation_id="conversation_test"), CapturingEvents()
    )

    messages = model.calls[1][0]
    assert history.contexts
    conversation = [(message.role, message.content) for message in messages]
    history_start = conversation.index(("user", "[historical_message]\nEarlier request"))
    assert conversation[history_start : history_start + 3] == [
        ("user", "[historical_message]\nEarlier request"),
        ("assistant", "[historical_message]\nEarlier answer"),
        ("user", "Prepare release notes"),
    ]
    assert not any("<conversation_history>" in (content or "") for _, content in conversation)


@pytest.mark.asyncio
async def test_capability_execution_rejects_unloaded_and_executable_skills() -> None:
    session = CapabilitySession(profile().skills)

    assert (await session.execute("skill_test"))["code"] == "SKILL_INSTRUCTIONS_NOT_LOADED"
    await session.search("load", None, "skill_test")
    assert (await session.execute("skill_test"))["status"] == "instruction_ready"

    executable = RuntimeSkillProfile(
        id="skill_executable",
        name="unsafe",
        description="unsafe",
        instructions="",
        manifest={"runtime": {"type": "python", "entrypoint": "run.py"}},
        version=1,
    )
    executable_session = CapabilitySession((executable,))
    await executable_session.search("load", None, executable.id)
    assert (await executable_session.execute(executable.id))[
        "code"
    ] == "SKILL_EXECUTION_NOT_ENABLED"
