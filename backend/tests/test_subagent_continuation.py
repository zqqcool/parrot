from __future__ import annotations

from dataclasses import replace

import pytest
from _agent_runtime_support import CapturingEvents, FakeModel, profile, request

from app.modules.agent_runtime.contracts import ChatCompletion, ChatMessage, ToolCall
from app.modules.agent_runtime.in_process import InProcessAgentRuntime
from app.modules.agent_runtime.planner import AgentPlanner, AgentPlanProtocolError
from app.modules.agent_runtime.resume_snapshot import create_resume_snapshot
from app.modules.agent_runtime.subagent_result import normalize_child_result
from app.modules.agent_runtime.taskboard import create_task_board


@pytest.mark.asyncio
async def test_required_child_failure_resumes_parent_as_partial() -> None:
    board = create_task_board(
        {
            "tasks": [
                {
                    "id": "research",
                    "objective": "Research release notes",
                    "source_role": "latest_user_request",
                    "source_quote": "Prepare release notes",
                    "source_span": {"start": 0, "end": 21},
                }
            ]
        },
        "Prepare release notes",
        0,
        source="agent_loop",
        dispatch_call_id="call_subagents_1",
        resume_plan={"action": "capability_lookup"},
    )
    board.settle("research", "failed", {"code": "CHILD_FAILED"})
    model = FakeModel([ChatCompletion(content="I could not obtain the delegated evidence.")])
    events = CapturingEvents()
    runtime = InProcessAgentRuntime(model, max_tool_rounds=3, timeout_seconds=30)

    await runtime.execute(
        replace(
            request(),
            profile=replace(profile(), skills=()),
            task_board=board.to_dict(),
            resume_messages=create_resume_snapshot(
                [ChatMessage(role="user", content="Prepare release notes")]
            ),
        ),
        events,
    )

    completed = next(data for event, data in events.items if event == "ai.output.completed")
    assert completed["runtime_status"] == "partial"
    assert completed["partial_reason"] == "required_subagent_failed"


def test_child_result_schema_is_validated_before_parent_resume() -> None:
    status, result = normalize_child_result(
        "completed",
        {"content": '{"answer":"ready"}'},
        {
            "type": "object",
            "properties": {"answer": {"type": "string"}},
            "required": ["answer"],
            "additionalProperties": False,
        },
    )

    assert status == "completed"
    assert result["structured_output"] == {"answer": "ready"}

    failed_status, failed_result = normalize_child_result(
        "completed",
        {"content": "not json"},
        {"type": "object"},
    )
    assert failed_status == "failed"
    assert failed_result["code"] == "SUBAGENT_RESULT_SCHEMA_INVALID"


@pytest.mark.asyncio
async def test_functional_planner_keeps_its_existing_multi_task_contract() -> None:
    model = FakeModel(
        [
            ChatCompletion(
                content=(
                    '{"action":"subagent_dispatch","tasks":['
                    '{"objective":"Research release notes",'
                    '"source_role":"latest_user_request",'
                    '"source_quote":"Prepare release notes",'
                    '"source_span":{"start":0,"end":21}}]}'
                )
            )
        ]
    )

    with pytest.raises(AgentPlanProtocolError, match="tasks are invalid"):
        await AgentPlanner(model).plan(profile(), "Prepare release notes")


@pytest.mark.asyncio
async def test_invalid_loop_resume_snapshot_fails_safe_without_calling_model() -> None:
    board = create_task_board(
        {
            "tasks": [
                {
                    "objective": "Research release notes",
                    "source_role": "latest_user_request",
                    "source_quote": "Prepare release notes",
                    "source_span": {"start": 0, "end": 21},
                }
            ]
        },
        "Prepare release notes",
        0,
        source="agent_loop",
        dispatch_call_id="call_subagents_1",
        resume_plan={"action": "agent_loop"},
    )
    board.settle("task_1", "completed", {"content": "evidence"})
    model = FakeModel([])
    events = CapturingEvents()

    await InProcessAgentRuntime(model, max_tool_rounds=3, timeout_seconds=30).execute(
        replace(
            request(),
            task_board=board.to_dict(),
            resume_messages=({"role": "invalid", "content": "unsafe"},),
        ),
        events,
    )

    assert model.calls == []
    completed = next(data for event, data in events.items if event == "ai.output.completed")
    assert completed["runtime_status"] == "partial"
    assert completed["partial_reason"] == "subagent_resume_context_invalid"


def test_subagent_result_schema_rejects_remote_references() -> None:
    with pytest.raises(ValueError, match="result schema is invalid"):
        create_task_board(
            {
                "tasks": [
                    {
                        "objective": "Research release notes",
                        "result_schema": {
                            "type": "object",
                            "properties": {"answer": {"$ref": "https://example.test/schema"}},
                        },
                        "source_role": "latest_user_request",
                        "source_quote": "Prepare release notes",
                        "source_span": {"start": 0, "end": 21},
                    }
                ]
            },
            "Prepare release notes",
            0,
        )


@pytest.mark.asyncio
async def test_parent_can_continue_using_tools_after_subagent_result() -> None:
    board = create_task_board(
        {
            "tasks": [
                {
                    "objective": "Research release notes",
                    "source_role": "latest_user_request",
                    "source_quote": "Prepare release notes",
                    "source_span": {"start": 0, "end": 21},
                }
            ]
        },
        "Prepare release notes",
        0,
        source="agent_loop",
        dispatch_call_id="call_subagents_1",
        resume_plan={"action": "agent_loop"},
    )
    board.settle("task_1", "completed", {"content": "research evidence"})
    model = FakeModel(
        [
            ChatCompletion(
                content=None,
                tool_calls=(ToolCall(id="call_time", name="time", arguments={"action": "now"}),),
            ),
            ChatCompletion(content="Final answer after checking time."),
        ]
    )
    events = CapturingEvents()

    await InProcessAgentRuntime(model, max_tool_rounds=3, timeout_seconds=30).execute(
        replace(
            request(),
            profile=replace(profile(), skills=()),
            task_board=board.to_dict(),
            resume_messages=create_resume_snapshot(
                [ChatMessage(role="user", content="Prepare release notes")]
            ),
        ),
        events,
    )

    assert len(model.calls) == 2
    assert model.calls[0][0][-1].name == "subagent_dispatch"
    assert model.calls[1][0][-1].name == "time"
    assert [event for event, _ in events.items].count("ai.output.completed") == 1
