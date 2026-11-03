from __future__ import annotations

import json

from app.modules.agent_runtime.contracts import ChatMessage, ToolCall
from app.modules.agent_runtime.planner import AgentPlan
from app.modules.agent_runtime.taskboard import (
    TaskBoard,
    TaskBoardTask,
    completed_task_board,
)

_MAX_RESULT_CONTENT = 16_000


def is_loop_taskboard(board: TaskBoard) -> bool:
    return board.source == "agent_loop" and board.dispatch_call_id is not None


def resumed_plan(board: TaskBoard) -> AgentPlan:
    action = (
        "agent_loop" if board.resume_plan.get("action") == "agent_loop" else "capability_lookup"
    )
    return AgentPlan(
        action=action,
        synthetic=True,
        # A settled Subagent Tool Result is already a runtime observation. The
        # completion gate must not require an unrelated second capability call.
        capability_prefetched=True,
    )


def subagent_terminal_metadata(
    value: dict[str, object] | None,
) -> tuple[str, dict[str, object]]:
    board = completed_task_board(value)
    if board is None or not any(
        task.required and task.status != "completed" for task in board.tasks
    ):
        return "completed", {}
    return "partial", {"partial_reason": "required_subagent_failed"}


def append_loop_continuation(messages: list[ChatMessage], board: TaskBoard) -> None:
    if not is_loop_taskboard(board):
        raise ValueError("TaskBoard is not resumable from the Agent Loop")
    call_id = board.dispatch_call_id
    if call_id is None:
        raise ValueError("TaskBoard dispatch call ID is missing")
    messages.append(
        ChatMessage(
            role="assistant",
            content=None,
            tool_calls=(
                ToolCall(
                    id=call_id,
                    name="subagent_dispatch",
                    arguments={"tasks": [_task_argument(task) for task in board.tasks]},
                ),
            ),
        )
    )
    messages.append(
        ChatMessage(
            role="tool",
            name="subagent_dispatch",
            tool_call_id=call_id,
            content=json.dumps(
                {"status": "ok", "results": [_result(task) for task in board.tasks]},
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        )
    )


def _task_argument(task: TaskBoardTask) -> dict[str, object]:
    return {
        "id": task.id,
        "objective": task.objective,
        "depends_on": list(task.depends_on),
        **task.source_provenance,
    }


def _result(task: TaskBoardTask) -> dict[str, object]:
    raw = task.result or {}
    content = raw.get("content")
    code = raw.get("code")
    structured = raw.get("structured_output")
    return {
        "schema_version": 1,
        "task_id": task.id,
        "status": _result_status(task.status),
        "content": content[:_MAX_RESULT_CONTENT] if isinstance(content, str) else None,
        "structured_output": structured if isinstance(structured, dict) else None,
        "error_code": code if isinstance(code, str) else None,
    }


def _result_status(status: str) -> str:
    if status == "completed":
        return "succeeded"
    return status if status in {"failed", "cancelled"} else "failed"
