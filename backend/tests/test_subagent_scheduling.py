from __future__ import annotations

from dataclasses import replace

from _agent_runtime_support import profile

from app.core.agent_runtime import RuntimeMcpServerProfile, RuntimeMcpToolPolicy
from app.modules.agent_runtime.subagent_scheduling import select_spawnable_tasks
from app.modules.agent_runtime.taskboard import create_task_board


def test_shared_non_parallel_mcp_scope_serializes_children() -> None:
    parent = replace(profile(), mcp_servers=(_server(parallel_safe=False),))
    board = _board()

    selected = select_spawnable_tasks(parent, board.ready_tasks(), ())

    assert [task.id for task in selected] == ["first"]


def test_shared_parallel_safe_mcp_scope_allows_independent_children() -> None:
    parent = replace(profile(), mcp_servers=(_server(parallel_safe=True),))
    board = _board()

    selected = select_spawnable_tasks(parent, board.ready_tasks(), ())

    assert [task.id for task in selected] == ["first", "second"]


def test_unknown_shared_mcp_scope_fails_closed_to_serial_scheduling() -> None:
    board = _board()

    selected = select_spawnable_tasks(profile(), board.ready_tasks(), ())

    assert [task.id for task in selected] == ["first"]


def _board():
    tasks = []
    for task_id in ("first", "second"):
        tasks.append(
            {
                "id": task_id,
                "objective": f"{task_id} research",
                "capability_scope": {
                    "mcp_capability_ids": ["mcp:docs:search"],
                },
                "source_role": "latest_user_request",
                "source_quote": "Prepare release notes",
                "source_span": {"start": 0, "end": 21},
            }
        )
    return create_task_board(
        {"tasks": tasks},
        "Prepare release notes",
        0,
        source="agent_loop",
        dispatch_call_id="call_subagents",
    )


def _server(*, parallel_safe: bool) -> RuntimeMcpServerProfile:
    return RuntimeMcpServerProfile(
        id="docs",
        name="Docs",
        transport="streamable_http",
        endpoint="https://example.test/mcp",
        arguments=(),
        encrypted_credentials=(),
        tool_policies=(
            RuntimeMcpToolPolicy(
                name="search",
                description="Search",
                input_schema={"type": "object"},
                schema_hash="sha256:test",
                effect="read",
                approval="automatic",
                parallel_safe=parallel_safe,
            ),
        ),
    )
