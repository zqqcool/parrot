from __future__ import annotations

from dataclasses import replace

import pytest
from _agent_runtime_support import CapturingEvents, FakeModel, profile, request

from app.modules.agent_runtime.contracts import ChatCompletion, ToolCall
from app.modules.agent_runtime.diagnostics import RuntimeDiagnostics
from app.modules.agent_runtime.in_process import InProcessAgentRuntime
from app.modules.interactions.runtime import RuntimeActiveSkill, RuntimeSkillContext


@pytest.mark.asyncio
async def test_capability_diagnostics_record_identity_without_private_instructions() -> None:
    events = CapturingEvents()
    diagnostics = RuntimeDiagnostics(request(), events)
    call = ToolCall(
        id="call_supporting",
        name="capability_search",
        arguments={
            "action": "load",
            "capability_id": "skill_supporting",
            "role": "supporting",
        },
    )

    await diagnostics.tool_call(call)
    await diagnostics.tool_result(
        call,
        {
            "status": "ok",
            "role": "supporting",
            "capability": {"id": "skill_supporting", "version": 2},
            "instructions": "private instructions",
        },
    )

    assert events.traces == [
        (
            "tool.call",
            {
                "tool_call_id": "call_supporting",
                "name": "capability_search",
                "argument_count": 3,
                "capability_id": "skill_supporting",
                "skill_role": "supporting",
            },
        ),
        (
            "tool.result",
            {
                "tool_call_id": "call_supporting",
                "name": "capability_search",
                "status": "ok",
                "code": "",
                "capability_id": "skill_supporting",
                "skill_version": 2,
                "skill_role": "supporting",
            },
        ),
    ]
    assert "private instructions" not in str(events.traces)


@pytest.mark.asyncio
async def test_functional_completion_receives_the_restored_skill_context() -> None:
    primary = profile().skills[0]
    supporting = replace(
        primary,
        id="skill_supporting",
        name="supporting",
        instructions="Provide supporting compliance constraints.",
    )
    context = RuntimeSkillContext(
        primary=RuntimeActiveSkill(primary.id, primary.version),
        supporting=(RuntimeActiveSkill(supporting.id, supporting.version),),
    )
    model = FakeModel(
        [
            ChatCompletion(content='{"action":"direct_answer"}'),
            ChatCompletion(content="Done."),
        ]
    )
    runtime = InProcessAgentRuntime(model, max_tool_rounds=2, timeout_seconds=30)

    await runtime.execute(
        replace(
            request(),
            profile=replace(profile(), skills=(primary, supporting)),
            active_skill=context.primary,
            skill_context=context,
        ),
        CapturingEvents(),
    )

    completion_messages = model.calls[1][0]
    assert any(
        "Produce concise release notes from supplied data." in (message.content or "")
        for message in completion_messages
    )
    assert any(
        "Provide supporting compliance constraints." in (message.content or "")
        for message in completion_messages
    )
