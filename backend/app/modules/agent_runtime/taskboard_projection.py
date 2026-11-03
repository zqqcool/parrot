from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from app.modules.agent_runtime.taskboard import TaskBoard


@dataclass(frozen=True)
class TaskBoardTaskProjection:
    id: str
    title: str
    objective: str
    kind: str
    depends_on: tuple[str, ...]
    status: str
    child_interaction_id: str | None
    result_summary: str | None


@dataclass(frozen=True)
class TaskBoardProjection:
    id: str | None
    status: str
    tasks: tuple[TaskBoardTaskProjection, ...]


def project_task_board(input_payload: Mapping[str, object]) -> TaskBoardProjection:
    raw_board = input_payload.get("task_board")
    if not isinstance(raw_board, dict):
        return TaskBoardProjection(id=None, status="not_generated", tasks=())
    try:
        board = TaskBoard.from_dict(cast(dict[str, object], raw_board))
    except ValueError:
        return TaskBoardProjection(id=None, status="unavailable", tasks=())
    return TaskBoardProjection(
        id=board.id,
        status=board.status,
        tasks=tuple(
            TaskBoardTaskProjection(
                id=task.id,
                title=task.title,
                objective=task.objective,
                kind=task.kind,
                depends_on=task.depends_on,
                status=task.status,
                child_interaction_id=task.child_interaction_id,
                result_summary=_result_summary(task.result),
            )
            for task in board.tasks
        ),
    )


def _result_summary(result: dict[str, object] | None) -> str | None:
    if result is None:
        return None
    content = result.get("content")
    if isinstance(content, str) and content.strip():
        return content.strip()[:1_000]
    code = result.get("code")
    return code if isinstance(code, str) and code else None
