from __future__ import annotations

from typing import cast

from app.core.agent_runtime import AgentRuntimeProfile
from app.modules.agent_runtime.taskboard import TaskBoardTask


def select_spawnable_tasks(
    profile: AgentRuntimeProfile,
    candidates: tuple[TaskBoardTask, ...],
    active: tuple[TaskBoardTask, ...],
) -> tuple[TaskBoardTask, ...]:
    safe = _parallel_safe_capability_ids(profile)
    reserved: set[str] = set()
    for task in active:
        reserved.update(_task_capabilities(task) - safe)
    selected: list[TaskBoardTask] = []
    for task in candidates:
        task_unsafe = _task_capabilities(task) - safe
        if task_unsafe & reserved:
            continue
        selected.append(task)
        reserved.update(task_unsafe)
    return tuple(selected)


def _parallel_safe_capability_ids(profile: AgentRuntimeProfile) -> set[str]:
    return {
        f"mcp:{server.id}:{policy.name}"
        for server in profile.mcp_servers
        for policy in server.tool_policies
        if (policy.effect == "read" and policy.approval == "automatic" and policy.parallel_safe)
    }


def _task_capabilities(task: TaskBoardTask) -> set[str]:
    value = task.capability_scope.get("mcp_capability_ids", [])
    if not isinstance(value, list):
        return set()
    return {item for item in cast(list[object], value) if isinstance(item, str)}
