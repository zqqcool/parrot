from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
from _agent_runtime_support import (
    CapturingEvents,
    FakeModel,
    FakeSubagentDispatcher,
    profile,
    request,
)

from app.core.config import AppConfig
from app.core.task_dispatch import TaskDispatcher
from app.infrastructure.db.session import DatabaseManager
from app.modules.agent_runtime.contracts import ChatCompletion, ChatMessage, ToolCall
from app.modules.agent_runtime.in_process import InProcessAgentRuntime
from app.modules.agent_runtime.plan_tools import tools_for_plan
from app.modules.agent_runtime.planner import AgentPlan
from app.modules.agent_runtime.resume_snapshot import (
    ResumeSnapshotTooLarge,
    create_resume_snapshot,
    restore_resume_snapshot,
)
from app.modules.agent_runtime.runtime_budget import execution_budget
from app.modules.agent_runtime.subagent_dispatcher import SqlSubagentDispatcher
from app.modules.agent_runtime.subagent_tools import subagent_dispatch_tool
from app.modules.agent_runtime.taskboard import create_task_board


def test_taskboard_preserves_the_delegated_task_kind() -> None:
    board = create_task_board(
        {
            "tasks": [
                {
                    "id": "review",
                    "objective": "Review the selected implementation.",
                    "kind": "code_review",
                    "source_role": "latest_user_request",
                    "source_quote": "Review the selected implementation.",
                    "source_span": {"start": 0, "end": 35},
                },
                {
                    "id": "tests",
                    "objective": "Run focused tests for the selected implementation.",
                    "kind": "test",
                    "source_role": "latest_user_request",
                    "source_quote": "Run focused tests for the selected implementation.",
                    "source_span": {"start": 36, "end": 86},
                },
            ]
        },
        "Review the selected implementation. Run focused tests for the selected implementation.",
        depth=0,
    )

    assert [task.kind for task in board.tasks] == ["code_review", "test"]
    assert [task.kind for task in board.from_dict(board.to_dict()).tasks] == ["code_review", "test"]
    assert all("agent_id" not in task.to_dict() for task in board.tasks)


def test_subagent_runtime_budget_is_capped_by_the_parent_policy() -> None:
    delegated = replace(
        request(),
        runtime_depth=1,
        subagent_task={"budget": {"timeout_seconds": 30, "max_tool_calls": 2}},
    )

    budget = execution_budget(
        delegated,
        timeout_seconds=90,
        max_tool_rounds=6,
        max_tool_calls=12,
        max_consecutive_tool_errors=3,
    )

    assert budget.timeout_seconds == 30
    assert budget.max_tool_calls == 2
    assert budget.max_tool_rounds == 6


def test_loop_resume_snapshot_is_bounded_and_excludes_private_reasoning() -> None:
    messages = [
        ChatMessage(role="system", content="policy"),
        ChatMessage(role="assistant", content="observed", reasoning_content="private"),
        ChatMessage(
            role="assistant",
            content=None,
            tool_calls=(
                ToolCall(id="delegate", name="subagent_dispatch", arguments={"tasks": []}),
            ),
            reasoning_content="private dispatch reasoning",
        ),
    ]

    snapshot = create_resume_snapshot(messages)
    restored = restore_resume_snapshot(snapshot)

    assert [message.content for message in restored] == ["policy", "observed"]
    assert all(message.reasoning_content is None for message in restored)
    with pytest.raises(ResumeSnapshotTooLarge):
        create_resume_snapshot(messages, max_bytes=8)


def test_subagent_tool_inherits_the_parent_agent_configuration() -> None:
    tool = subagent_dispatch_tool()
    task = {
        "objective": "Review the implementation",
        "source_role": "latest_user_request",
        "source_quote": "Review the implementation",
        "source_span": {"start": 0, "end": 25},
    }

    assert tool.accepts_arguments({"tasks": [task]})
    assert not tool.accepts_arguments({"tasks": [{**task, "agent_id": "agent_other"}]})


def test_knowledge_root_exposes_subagent_dispatch_when_enabled() -> None:
    knowledge_request = replace(request(), profile=replace(profile(), agent_type_key="knowledge"))

    tools = tools_for_plan(
        knowledge_request,
        AgentPlan(action="agent_loop", synthetic=True),
        script_enabled=False,
        subagent_enabled=True,
    )

    assert "subagent_dispatch" in {tool.name for tool in tools}


def test_functional_root_loop_exposes_subagent_without_changing_planner() -> None:
    tools = tools_for_plan(
        request(),
        AgentPlan(action="agent_loop"),
        script_enabled=False,
        subagent_enabled=True,
    )

    assert "subagent_dispatch" in {tool.name for tool in tools}


def test_subagent_contract_accepts_one_bounded_result_task() -> None:
    task: dict[str, object] = {
        "id": "research",
        "objective": "Research release notes",
        "source_role": "latest_user_request",
        "source_quote": "Prepare release notes",
        "source_span": {"start": 0, "end": 21},
    }
    tasks = [task]
    arguments: dict[str, object] = {"tasks": tasks}
    tool = subagent_dispatch_tool(max_tasks=1)
    board = create_task_board(
        arguments,
        "Prepare release notes",
        depth=0,
        source="agent_loop",
        dispatch_call_id="call_subagents_1",
        resume_plan={"action": "capability_lookup"},
    )

    assert tool.accepts_arguments(arguments)
    assert not tool.accepts_arguments({"tasks": []})
    assert not tool.accepts_arguments({"tasks": [*tasks, *tasks]})
    assert [task.id for task in board.tasks] == ["research"]


def test_loop_taskboard_persists_its_resume_contract() -> None:
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
        depth=0,
        source="agent_loop",
        dispatch_call_id="call_subagents_1",
        resume_plan={"action": "agent_loop"},
    )

    restored = board.from_dict(board.to_dict())
    assert restored.source == "agent_loop"
    assert restored.dispatch_call_id == "call_subagents_1"
    assert restored.resume_plan == {"action": "agent_loop"}


def test_subagent_task_preserves_required_scope_and_result_schema() -> None:
    arguments: dict[str, object] = {
        "tasks": [
            {
                "id": "research",
                "objective": "Research release notes",
                "required": False,
                "capability_scope": {
                    "supporting_skills": [{"skill_id": "skill_test", "skill_version": 1}],
                    "mcp_capability_ids": ["mcp:server_test:lookup"],
                    "knowledge_enabled": True,
                },
                "result_schema": {"type": "object"},
                "source_role": "latest_user_request",
                "source_quote": "Prepare release notes",
                "source_span": {"start": 0, "end": 21},
            }
        ]
    }
    board = create_task_board(arguments, "Prepare release notes", depth=0)

    task = board.from_dict(board.to_dict()).tasks[0]
    assert subagent_dispatch_tool().accepts_arguments(arguments)
    assert task.required is False
    assert task.capability_scope["knowledge_enabled"] is True
    assert task.result_schema == {"type": "object"}


@pytest.mark.asyncio
@pytest.mark.parametrize(("enabled", "expected"), [(True, True), (False, False)])
async def test_loop_subagent_rollout_switch_controls_tool_visibility(
    enabled: bool, expected: bool
) -> None:
    model = FakeModel(
        [
            ChatCompletion(content='{"action":"capability_lookup"}'),
            ChatCompletion(
                content=None,
                tool_calls=(ToolCall(id="call_time", name="time", arguments={"action": "now"}),),
            ),
            ChatCompletion(content="Time checked."),
        ]
    )
    runtime = InProcessAgentRuntime(
        model,
        max_tool_rounds=2,
        timeout_seconds=30,
        subagent_dispatcher=FakeSubagentDispatcher(),
        loop_subagents_enabled=enabled,
    )

    await runtime.execute(request(), CapturingEvents())

    visible = {tool.name for tool in model.calls[1][1]}
    assert ("subagent_dispatch" in visible) is expected


@pytest.mark.asyncio
async def test_subagent_uses_a_synthetic_plan_without_a_planner_model_call() -> None:
    model = FakeModel(
        [
            ChatCompletion(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="call_find",
                        name="capability_search",
                        arguments={"action": "find", "query": ""},
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
            ChatCompletion(content="Delegated task complete."),
        ]
    )
    runtime = InProcessAgentRuntime(model, max_tool_rounds=3, timeout_seconds=30)
    events = CapturingEvents()
    delegated = replace(
        request(),
        runtime_depth=1,
        entry_type="subagent",
        subagent_task={
            "id": "task_review",
            "kind": "code_review",
            "tool_hints": ["repository inspection"],
            "budget": {"timeout_seconds": 30, "max_tool_calls": 4},
        },
    )

    await runtime.execute(delegated, events)

    assert len(model.calls) == 4
    plan_events = [
        data for event_type, data in events.items if event_type == "ai.agent.plan.created"
    ]
    assert plan_events == [{"action": "capability_lookup", "synthetic": True}]
    assert "capability_search" in [tool.name for tool in model.calls[0][1]]


@pytest.mark.asyncio
async def test_subagent_budget_limits_total_tool_calls() -> None:
    model = FakeModel(
        [
            ChatCompletion(
                content=None,
                tool_calls=(
                    ToolCall(id="time", name="time", arguments={"action": "now"}),
                    ToolCall(
                        id="math",
                        name="math",
                        arguments={"action": "evaluate", "expression": "1 + 1"},
                    ),
                ),
            ),
            ChatCompletion(content="Partial delegated result."),
        ]
    )
    runtime = InProcessAgentRuntime(model, max_tool_rounds=3, max_tool_calls=12, timeout_seconds=30)
    events = CapturingEvents()
    delegated = replace(
        request(),
        profile=replace(profile(), skills=()),
        runtime_depth=1,
        entry_type="subagent",
        subagent_task={"budget": {"timeout_seconds": 30, "max_tool_calls": 1}},
    )

    await runtime.execute(delegated, events)

    assert events.items[-1][0] == "ai.output.completed"
    assert events.items[-1][1]["runtime_status"] == "partial"
    assert events.items[-1][1]["budget_reason"] == "max_tool_calls_exceeded"


@pytest.mark.asyncio
async def test_completed_loop_taskboard_uses_the_bounded_snapshot_for_final_join() -> None:
    board = create_task_board(
        {
            "tasks": [
                {
                    "id": "research",
                    "objective": "Research the release evidence",
                    "source_role": "latest_user_request",
                    "source_quote": "Prepare release notes",
                    "source_span": {"start": 0, "end": 21},
                },
                {
                    "id": "review",
                    "objective": "Review the release evidence",
                    "source_role": "latest_user_request",
                    "source_quote": "Prepare release notes",
                    "source_span": {"start": 0, "end": 21},
                },
            ]
        },
        "Prepare release notes",
        depth=0,
        source="agent_loop",
        dispatch_call_id="call_subagents_1",
        resume_plan={"action": "capability_lookup"},
    )
    for task in board.tasks:
        board.settle(task.id, "completed", {"content": f"{task.id} result"})
    snapshot = create_resume_snapshot(
        [
            ChatMessage(role="system", content="root policy"),
            ChatMessage(role="user", content="Prepare release notes"),
            ChatMessage(role="tool", content="prior evidence", name="knowledge_search"),
        ]
    )
    model = FakeModel([ChatCompletion(content="Joined child results.")])
    runtime = InProcessAgentRuntime(model, max_tool_rounds=3, timeout_seconds=30)
    events = CapturingEvents()

    await runtime.execute(
        replace(request(), task_board=board.to_dict(), resume_messages=snapshot),
        events,
    )

    assert len(model.calls) == 1
    final_messages = model.calls[0][0]
    assert any(message.content == "prior evidence" for message in final_messages)
    assert final_messages[-2].role == "assistant"
    assert final_messages[-2].tool_calls[0].id == "call_subagents_1"
    assert final_messages[-1].role == "tool"
    assert final_messages[-1].tool_call_id == "call_subagents_1"
    assert '"task_id":"research"' in (final_messages[-1].content or "")
    assert "capability_search" in {tool.name for tool in model.calls[0][1]}
    assert events.items[-1][1]["content"] == "Joined child results."


@pytest.mark.asyncio
async def test_last_subagent_requeues_parent_for_result_aggregation() -> None:
    queue = SimpleNamespace(dispatch_runtime=AsyncMock())
    dispatcher = SqlSubagentDispatcher(
        cast(AppConfig, SimpleNamespace()),
        cast(DatabaseManager, SimpleNamespace()),
        cast(TaskDispatcher, queue),
    )
    dispatcher._settle = AsyncMock(  # pyright: ignore[reportPrivateUsage]
        return_value={
            "board_id": "board_1",
            "task_id": "draft",
            "task_status": "completed",
            "child_interaction_ids": (),
            "all_terminal": True,
        }
    )
    child_request = replace(
        request(), parent_interaction_id="interaction_parent", subagent_task_id="draft"
    )

    await dispatcher.settle_child(child_request, CapturingEvents())

    queue.dispatch_runtime.assert_awaited_once_with("tenant_test", "interaction_parent")
