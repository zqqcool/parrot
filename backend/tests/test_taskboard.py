from __future__ import annotations

import pytest

from app.modules.agent_runtime.subagent_task_prompt import render_task_contract
from app.modules.agent_runtime.taskboard import create_task_board


def test_taskboard_enforces_latest_user_request_provenance_and_dependencies() -> None:
    user_text = "Compare alpha and beta"
    board = create_task_board(
        {
            "tasks": [
                {
                    "id": "alpha",
                    "objective": "Analyze alpha",
                    "source_role": "latest_user_request",
                    "source_quote": "Compare alpha",
                    "source_span": {"start": 0, "end": 13},
                },
                {
                    "id": "beta",
                    "objective": "Compare beta after alpha",
                    "depends_on": ["alpha"],
                    "source_role": "latest_user_request",
                    "source_quote": "beta",
                    "source_span": {"start": 18, "end": 22},
                },
            ]
        },
        user_text,
        0,
    )

    assert [task.id for task in board.ready_tasks()] == ["alpha"]
    board.mark_child("alpha", "interaction_alpha")
    board.settle("alpha", "completed", {"content": "alpha result"})
    assert [task.id for task in board.ready_tasks()] == ["beta"]


def test_taskboard_rejects_unanchored_tasks() -> None:
    with pytest.raises(ValueError, match="latest user request"):
        create_task_board(
            {"tasks": [_task(), _task()]},
            "Analyze this request",
            0,
        )


def test_dependent_task_receives_only_declared_results_as_reference_data() -> None:
    board = create_task_board(
        {
            "tasks": [
                _anchored("research", "Research release notes"),
                {
                    **_anchored("review", "Review release notes"),
                    "depends_on": ["research"],
                },
                _anchored("unrelated", "Check unrelated notes"),
            ]
        },
        "Prepare release notes",
        0,
    )
    board.settle("research", "completed", {"content": "research evidence"})
    board.settle("unrelated", "completed", {"content": "unrelated evidence"})

    task = next(item for item in board.tasks if item.id == "review")
    contract = render_task_contract(task, board.dependency_results(task))

    assert "<dependency_results>" in contract
    assert "research evidence" in contract
    assert "unrelated evidence" not in contract


def test_required_failure_cancels_blocked_dependents_and_settles_board() -> None:
    board = create_task_board(
        {
            "tasks": [
                _anchored("research", "Research release notes"),
                {
                    **_anchored("review", "Review release notes"),
                    "depends_on": ["research"],
                },
            ]
        },
        "Prepare release notes",
        0,
    )

    board.settle("research", "failed", {"code": "CHILD_FAILED"})

    review = next(item for item in board.tasks if item.id == "review")
    assert review.status == "cancelled"
    assert review.result == {"code": "SUBAGENT_DEPENDENCY_FAILED"}
    assert board.all_terminal()


def test_optional_failure_is_available_to_declared_dependents() -> None:
    board = create_task_board(
        {
            "tasks": [
                {**_anchored("research", "Research release notes"), "required": False},
                {
                    **_anchored("review", "Review release notes"),
                    "depends_on": ["research"],
                },
            ]
        },
        "Prepare release notes",
        0,
    )

    board.settle("research", "failed", {"code": "OPTIONAL_SOURCE_FAILED"})

    assert [task.id for task in board.ready_tasks()] == ["review"]


def test_taskboard_applies_configured_task_and_parallel_limits() -> None:
    tasks = [
        _anchored("research", "Research release notes"),
        _anchored("review", "Review release notes"),
    ]

    with pytest.raises(ValueError, match="configured task limit"):
        create_task_board(
            {"tasks": tasks},
            "Prepare release notes",
            0,
            max_tasks=1,
            max_parallel=1,
        )

    board = create_task_board(
        {"tasks": tasks},
        "Prepare release notes",
        0,
        max_tasks=2,
        max_parallel=1,
    )
    assert [task.id for task in board.ready_tasks()] == ["research"]


def test_independent_tasks_are_ready_in_stable_definition_order() -> None:
    board = create_task_board(
        {
            "tasks": [
                _anchored("research", "Research release notes"),
                _anchored("review", "Review release notes"),
            ]
        },
        "Prepare release notes",
        0,
    )

    assert [task.id for task in board.ready_tasks()] == ["research", "review"]


def _task() -> dict[str, object]:
    return {
        "objective": "Analyze this request",
    }


def _anchored(task_id: str, objective: str) -> dict[str, object]:
    return {
        "id": task_id,
        "objective": objective,
        "source_role": "latest_user_request",
        "source_quote": "Prepare release notes",
        "source_span": {"start": 0, "end": 21},
    }
