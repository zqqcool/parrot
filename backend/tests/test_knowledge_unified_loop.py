from __future__ import annotations

from dataclasses import dataclass, replace

import pytest
from _agent_runtime_support import CapturingEvents, FakeModel, profile, request

from app.modules.agent_runtime.contracts import (
    ChatCompletion,
    ToolCall,
)
from app.modules.agent_runtime.in_process import InProcessAgentRuntime
from app.modules.interactions.history import ConversationHistoryMessage, ConversationTurn
from app.modules.interactions.runtime import (
    RuntimeActiveSkill,
    RuntimeControlState,
    RuntimeSkillContext,
)


@dataclass
class _ActiveSkillCheckpoints:
    active: RuntimeActiveSkill | None = None

    async def activate(
        self,
        *,
        tenant_id: str,
        interaction_id: str,
        skill_id: str,
        skill_version: int,
    ) -> bool:
        del tenant_id, interaction_id
        requested = RuntimeActiveSkill(skill_id=skill_id, skill_version=skill_version)
        if self.active is not None and self.active != requested:
            return False
        self.active = requested
        return True


class _SteeringReader:
    def __init__(self, message: str) -> None:
        self._message = message

    async def consume(self, runtime_request: object) -> RuntimeControlState:
        del runtime_request
        message, self._message = self._message, ""
        return RuntimeControlState(steering_messages=(message,) if message else ())


class _ResumeHistory:
    async def recent(
        self, context: object, *, turns: int, max_tokens: int
    ) -> tuple[ConversationTurn, ...]:
        del context, turns, max_tokens
        return ()

    async def resume_messages(
        self, context: object, *, through_sequence: int, max_tokens: int
    ) -> tuple[ConversationHistoryMessage, ...]:
        del context, through_sequence, max_tokens
        return (
            ConversationHistoryMessage("user", "Prepare release notes"),
            ConversationHistoryMessage("assistant", "请提供要发布的版本。"),
        )


@pytest.mark.asyncio
async def test_knowledge_request_enters_one_main_loop_with_on_demand_tools() -> None:
    model = FakeModel(
        [ChatCompletion(content="这是一个不需要检索的普通回答。")],
        auto_final_response=False,
    )
    runtime = InProcessAgentRuntime(model, max_tool_rounds=2, timeout_seconds=30)

    await runtime.execute(
        replace(request(), profile=replace(profile(), agent_type_key="knowledge")),
        CapturingEvents(),
    )

    assert len(model.calls) == 1
    messages, tools = model.calls[0]
    assert {tool.name for tool in tools} >= {
        "knowledge_search",
        "capability_search",
        "capability_execute",
        "ask_user",
        "final_response",
    }
    assert not any(
        "knowledge_capability_candidates" in (message.content or "") for message in messages
    )


@pytest.mark.asyncio
async def test_knowledge_request_restores_primary_and_supporting_skill_instructions() -> None:
    primary = profile().skills[0]
    supporting = replace(
        primary,
        id="skill_supporting",
        name="supporting",
        instructions="Provide current weather constraints.",
    )
    context = RuntimeSkillContext(
        primary=RuntimeActiveSkill(primary.id, primary.version),
        supporting=(RuntimeActiveSkill(supporting.id, supporting.version),),
    )
    model = FakeModel(
        [
            ChatCompletion(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="call_final",
                        name="final_response",
                        arguments={"content": "Combined result."},
                    ),
                ),
            )
        ],
        auto_final_response=False,
    )
    runtime = InProcessAgentRuntime(model, max_tool_rounds=2, timeout_seconds=30)
    knowledge_profile = replace(
        profile(),
        agent_type_key="knowledge",
        skills=(primary, supporting),
    )

    await runtime.execute(
        replace(
            request(),
            profile=knowledge_profile,
            active_skill=context.primary,
            skill_context=context,
        ),
        CapturingEvents(),
    )

    messages = model.calls[0][0]
    assert any(
        "Produce concise release notes from supplied data." in (message.content or "")
        for message in messages
    )
    assert any(
        "Provide current weather constraints." in (message.content or "") for message in messages
    )


@pytest.mark.asyncio
async def test_waiting_knowledge_flow_resumes_the_pinned_skill_without_recall() -> None:
    checkpoints = _ActiveSkillCheckpoints()
    model = FakeModel(
        [
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
                        arguments={"action": "load", "skill_id": "skill_test"},
                    ),
                ),
            ),
            ChatCompletion(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="call_wait",
                        name="ask_user",
                        arguments={"question": "请提供要发布的版本。"},
                    ),
                ),
            ),
            ChatCompletion(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="call_final",
                        name="final_response",
                        arguments={"content": "已按 release-notes Skill 继续处理版本 v2。"},
                    ),
                ),
            ),
        ],
        auto_final_response=False,
    )
    runtime = InProcessAgentRuntime(
        model,
        max_tool_rounds=4,
        timeout_seconds=30,
        active_skill_checkpoints=checkpoints,
        conversation_history=_ResumeHistory(),
    )
    knowledge_profile = replace(profile(), agent_type_key="knowledge")
    first_events = CapturingEvents()

    await runtime.execute(replace(request(), profile=knowledge_profile), first_events)

    assert checkpoints.active == RuntimeActiveSkill(skill_id="skill_test", skill_version=1)
    assert first_events.items[-1][1]["runtime_status"] == "waiting_user_input"

    resumed_events = CapturingEvents()
    await runtime.execute(
        replace(
            request(),
            profile=knowledge_profile,
            active_skill=checkpoints.active,
            resume_assistant_message="请提供要发布的版本。",
            control_after_sequence=5,
            conversation_id="conversation_test",
            control_reader=_SteeringReader("v2"),
        ),
        resumed_events,
    )

    resumed_messages = model.calls[-1][0]
    assert any(
        "Produce concise release notes from supplied data." in (message.content or "")
        for message in resumed_messages
    )
    resumed_calls = [
        call.name
        for message in resumed_messages
        for call in message.tool_calls
        if not call.id.startswith("resume_skill_context")
    ]
    assert "capability_search" not in resumed_calls
    relevant_messages = [
        (message.role, message.content)
        for message in resumed_messages
        if message.content in {"Prepare release notes", "请提供要发布的版本。", "v2"}
    ]
    assert relevant_messages == [
        ("user", "Prepare release notes"),
        ("assistant", "请提供要发布的版本。"),
        ("user", "v2"),
    ]
    assert len(model.calls) == 4
    assert resumed_events.items[-1][1]["content"] == ("已按 release-notes Skill 继续处理版本 v2。")


@pytest.mark.asyncio
async def test_active_skill_plain_text_is_delivered_without_a_repair_turn() -> None:
    checkpoints = _ActiveSkillCheckpoints()
    model = FakeModel(
        [
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
            ChatCompletion(content="请提供要发布的版本。"),
        ],
        auto_final_response=False,
    )
    events = CapturingEvents()
    runtime = InProcessAgentRuntime(
        model,
        max_tool_rounds=4,
        timeout_seconds=30,
        active_skill_checkpoints=checkpoints,
        capture_prompts=True,
    )

    await runtime.execute(
        replace(request(), profile=replace(profile(), agent_type_key="knowledge")),
        events,
    )

    assert len(model.calls) == 4
    assert model.tool_choices == [None, None, None, None]
    assert events.items[-1][1]["runtime_status"] == "completed"
    assert events.items[-1][1]["content"] == "请提供要发布的版本。"
    requests = [data for trace_type, data in events.traces if trace_type == "model.request"]
    assert all(item.get("tool_choice") is None for item in requests)


@pytest.mark.asyncio
async def test_reasoning_model_uses_provider_default_tool_selection() -> None:
    checkpoints = _ActiveSkillCheckpoints()
    model = FakeModel(
        [
            ChatCompletion(
                content=None,
                reasoning_content="Find the relevant workflow.",
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
                reasoning_content="Load the selected workflow.",
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
                        id="call_wait",
                        name="ask_user",
                        arguments={"question": "请提供要发布的版本。"},
                    ),
                ),
            ),
        ],
        auto_final_response=False,
    )
    events = CapturingEvents()
    runtime = InProcessAgentRuntime(
        model,
        max_tool_rounds=3,
        timeout_seconds=30,
        active_skill_checkpoints=checkpoints,
    )

    await runtime.execute(
        replace(request(), profile=replace(profile(), agent_type_key="knowledge")),
        events,
    )

    assert model.tool_choices == [None, None, None]
    assert events.items[-1][1]["runtime_status"] == "waiting_user_input"


@pytest.mark.asyncio
async def test_declared_thinking_model_never_requests_required_tool_choice() -> None:
    checkpoints = _ActiveSkillCheckpoints()
    model = FakeModel(
        [
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
                        arguments={"action": "load", "skill_id": "skill_test"},
                    ),
                ),
            ),
            ChatCompletion(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="call_wait",
                        name="ask_user",
                        arguments={"question": "请提供要发布的版本。"},
                    ),
                ),
            ),
        ],
        auto_final_response=False,
    )
    events = CapturingEvents()
    runtime = InProcessAgentRuntime(
        model,
        max_tool_rounds=3,
        timeout_seconds=30,
        active_skill_checkpoints=checkpoints,
    )
    runtime_profile = replace(
        profile(),
        agent_type_key="knowledge",
        llm=replace(profile().llm, thinking_enabled=True),
    )

    await runtime.execute(replace(request(), profile=runtime_profile), events)

    assert model.tool_choices == [None, None, None]
    assert events.items[-1][1]["runtime_status"] == "waiting_user_input"


@pytest.mark.asyncio
async def test_active_skill_loop_never_requests_required_tool_choice() -> None:
    checkpoints = _ActiveSkillCheckpoints()
    model = FakeModel(
        [
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
                        arguments={"action": "load", "skill_id": "skill_test"},
                    ),
                ),
            ),
            ChatCompletion(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="call_wait",
                        name="ask_user",
                        arguments={"question": "请提供要发布的版本。"},
                    ),
                ),
            ),
        ],
        auto_final_response=False,
    )
    events = CapturingEvents()
    runtime = InProcessAgentRuntime(
        model,
        max_tool_rounds=3,
        timeout_seconds=30,
        active_skill_checkpoints=checkpoints,
    )

    await runtime.execute(
        replace(request(), profile=replace(profile(), agent_type_key="knowledge")),
        events,
    )

    assert model.tool_choices == [None, None, None]
    assert events.items[-1][1]["runtime_status"] == "waiting_user_input"


@pytest.mark.asyncio
async def test_missing_pinned_skill_version_fails_closed_without_switching() -> None:
    model = FakeModel([], auto_final_response=False)
    events = CapturingEvents()
    runtime = InProcessAgentRuntime(model, max_tool_rounds=2, timeout_seconds=30)

    await runtime.execute(
        replace(
            request(),
            profile=replace(profile(), agent_type_key="knowledge"),
            active_skill=RuntimeActiveSkill(skill_id="skill_test", skill_version=999),
        ),
        events,
    )

    assert model.calls == []
    assert events.items[-1][1]["runtime_status"] == "partial"
    assert events.items[-1][1]["partial_reason"] == "active_skill_version_unavailable"
