from __future__ import annotations

from dataclasses import dataclass, replace

import pytest
from _agent_runtime_support import CapturingEvents, FakeModel, profile, request

from app.modules.agent_runtime.contracts import ChatCompletion, ToolCall
from app.modules.agent_runtime.in_process import InProcessAgentRuntime
from app.modules.interactions.runtime import RuntimeActiveSkill


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


@pytest.mark.asyncio
async def test_ranked_capability_candidates_remain_advisory() -> None:
    model = FakeModel(
        [
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
            ChatCompletion(content="No matching workflow is suitable for this request."),
        ],
        auto_final_response=False,
    )
    events = CapturingEvents()
    runtime = InProcessAgentRuntime(model, max_tool_rounds=3, timeout_seconds=30)

    await runtime.execute(
        replace(request(), profile=replace(profile(), agent_type_key="knowledge")),
        events,
    )

    assert model.tool_choices == [None, None]
    assert events.items[-1][1]["runtime_status"] == "completed"
    assert events.items[-1][1]["content"] == ("No matching workflow is suitable for this request.")


@pytest.mark.asyncio
async def test_ask_user_remains_valid_without_loading_a_ranked_candidate() -> None:
    model = FakeModel(
        [
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
            ChatCompletion(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="call_wait",
                        name="ask_user",
                        arguments={"question": "Which city?"},
                    ),
                ),
            ),
        ],
        auto_final_response=False,
    )
    events = CapturingEvents()
    runtime = InProcessAgentRuntime(model, max_tool_rounds=3, timeout_seconds=30)

    await runtime.execute(
        replace(request(), profile=replace(profile(), agent_type_key="knowledge")),
        events,
    )

    assert model.tool_choices == [None, None]
    assert events.items[-1][1]["runtime_status"] == "waiting_user_input"
    assert events.items[-1][1]["content"] == "Which city?"


@pytest.mark.asyncio
async def test_active_skill_plain_text_is_a_terminal_fallback_without_repair() -> None:
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
                        id="call_execute",
                        name="capability_execute",
                        arguments={"skill_id": "skill_test"},
                    ),
                ),
            ),
            ChatCompletion(content="请提供要发布的数据。"),
        ],
        auto_final_response=False,
    )
    events = CapturingEvents()
    runtime = InProcessAgentRuntime(
        model,
        max_tool_rounds=5,
        timeout_seconds=30,
        active_skill_checkpoints=checkpoints,
    )

    await runtime.execute(
        replace(request(), profile=replace(profile(), agent_type_key="knowledge")),
        events,
    )

    assert model.tool_choices == [None, None, None, None]
    assert events.items[-1][1]["runtime_status"] == "completed"
    assert events.items[-1][1]["content"] == "请提供要发布的数据。"
