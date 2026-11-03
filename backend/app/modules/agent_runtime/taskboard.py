from __future__ import annotations

from dataclasses import dataclass, field
from typing import cast

from app.core.ids import new_id
from app.modules.agent_runtime.subagent_schema import bounded_result_schema

_TERMINAL = frozenset({"completed", "failed", "cancelled"})
_MAX_CHILDREN = 5
_MAX_PARALLEL = 3
_MAX_DEPTH = 1
_MAX_TIMEOUT = 180
_MAX_TOOL_CALLS = 20


def _empty_mapping() -> dict[str, object]:
    return {}


@dataclass
class TaskBudget:
    timeout_seconds: int = 60
    max_tool_calls: int = 3

    def to_dict(self) -> dict[str, int]:
        return {"timeout_seconds": self.timeout_seconds, "max_tool_calls": self.max_tool_calls}

    @classmethod
    def from_value(cls, value: object) -> TaskBudget:
        data = cast(dict[str, object], value) if isinstance(value, dict) else {}
        timeout = _positive_int(data.get("timeout_seconds"), 60)
        tools = _positive_int(data.get("max_tool_calls"), 3)
        if timeout > _MAX_TIMEOUT or tools > _MAX_TOOL_CALLS:
            raise ValueError("subagent task budget exceeds runtime limits")
        return cls(timeout_seconds=timeout, max_tool_calls=tools)


@dataclass
class TaskBoardTask:
    id: str
    title: str
    objective: str
    kind: str = "general"
    depends_on: tuple[str, ...] = ()
    required: bool = True
    capability_scope: dict[str, object] = field(default_factory=_empty_mapping)
    budget: TaskBudget = field(default_factory=TaskBudget)
    result_schema: dict[str, object] = field(default_factory=_empty_mapping)
    tool_hints: tuple[str, ...] = ()
    source_hints: tuple[str, ...] = ()
    source_provenance: dict[str, object] = field(default_factory=_empty_mapping)
    dedupe_key: str = ""
    status: str = "ready"
    child_interaction_id: str | None = None
    result: dict[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "title": self.title,
            "objective": self.objective,
            "kind": self.kind,
            "depends_on": list(self.depends_on),
            "required": self.required,
            "capability_scope": self.capability_scope,
            "budget": self.budget.to_dict(),
            "result_schema": self.result_schema,
            "tool_hints": list(self.tool_hints),
            "source_hints": list(self.source_hints),
            "source_provenance": self.source_provenance,
            "dedupe_key": self.dedupe_key,
            "status": self.status,
            "child_interaction_id": self.child_interaction_id,
            "result": self.result,
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> TaskBoardTask:
        return cls(
            id=_required(value, "id", 64),
            title=_required(value, "title", 191),
            objective=_required(value, "objective", 8_000),
            kind=_task_kind(value.get("kind")),
            depends_on=_string_tuple(value.get("depends_on")),
            required=_boolean(value.get("required"), True),
            capability_scope=_mapping(value.get("capability_scope")),
            budget=TaskBudget.from_value(value.get("budget")),
            result_schema=bounded_result_schema(
                value.get("result_schema") or value.get("output_schema")
            ),
            tool_hints=_string_tuple(value.get("tool_hints")),
            source_hints=_string_tuple(value.get("source_hints")),
            source_provenance=_mapping(value.get("source_provenance")),
            dedupe_key=_text(value.get("dedupe_key")) or _required(value, "id", 64),
            status=_text(value.get("status")) or "ready",
            child_interaction_id=_optional_text(value.get("child_interaction_id")),
            result=_mapping_or_none(value.get("result")),
        )


@dataclass
class TaskBoard:
    id: str
    tasks: list[TaskBoardTask]
    status: str = "waiting_subagents"
    source: str = "planner"
    dispatch_call_id: str | None = None
    resume_plan: dict[str, object] = field(default_factory=_empty_mapping)
    max_parallel: int = _MAX_PARALLEL

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "status": self.status,
            "source": self.source,
            "dispatch_call_id": self.dispatch_call_id,
            "resume_plan": self.resume_plan,
            "max_parallel": self.max_parallel,
            "tasks": [task.to_dict() for task in self.tasks],
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> TaskBoard:
        raw_tasks = value.get("tasks")
        if not isinstance(raw_tasks, list):
            raise ValueError("TaskBoard tasks are invalid")
        tasks = cast(list[object], raw_tasks)
        parsed_tasks: list[TaskBoardTask] = []
        for raw_task in tasks:
            if not isinstance(raw_task, dict):
                raise ValueError("TaskBoard task is invalid")
            parsed_tasks.append(TaskBoardTask.from_dict(_mapping(cast(object, raw_task))))
        return cls(
            id=_required(value, "id", 64),
            status=_text(value.get("status")) or "waiting_subagents",
            source=_text(value.get("source")) or "planner",
            dispatch_call_id=_optional_text(value.get("dispatch_call_id")),
            resume_plan=_mapping(value.get("resume_plan")),
            max_parallel=_bounded_parallel(value.get("max_parallel")),
            tasks=parsed_tasks,
        )

    def ready_tasks(self) -> tuple[TaskBoardTask, ...]:
        satisfied = {
            task.id
            for task in self.tasks
            if task.status == "completed" or (not task.required and task.status in _TERMINAL)
        }
        active = sum(1 for task in self.tasks if task.status == "running")
        slots = max(0, self.max_parallel - active)
        return tuple(
            task
            for task in self.tasks
            if slots > 0
            if task.status == "ready"
            if task.child_interaction_id is None
            if all(dependency in satisfied for dependency in task.depends_on)
        )[:slots]

    def all_terminal(self) -> bool:
        return bool(self.tasks) and all(task.status in _TERMINAL for task in self.tasks)

    def dependency_results(self, task: TaskBoardTask) -> tuple[dict[str, object], ...]:
        dependencies = set(task.depends_on)
        return tuple(
            {
                "task_id": item.id,
                "status": item.status,
                "result": item.result or {},
            }
            for item in self.tasks
            if item.id in dependencies
        )

    def mark_child(self, task_id: str, child_interaction_id: str) -> None:
        task = self._task(task_id)
        task.child_interaction_id = child_interaction_id
        task.status = "running"

    def settle(self, task_id: str, status: str, result: dict[str, object]) -> None:
        task = self._task(task_id)
        task.status = status if status in _TERMINAL else "failed"
        task.result = result
        if task.required and task.status != "completed":
            self._cancel_blocked_dependents(task.id)
        self.status = "completed" if self.all_terminal() else "waiting_subagents"

    def _cancel_blocked_dependents(self, failed_task_id: str) -> None:
        blocked = {failed_task_id}
        changed = True
        while changed:
            changed = False
            for task in self.tasks:
                if task.status != "ready" or not blocked.intersection(task.depends_on):
                    continue
                task.status = "cancelled"
                task.result = {"code": "SUBAGENT_DEPENDENCY_FAILED"}
                blocked.add(task.id)
                changed = True

    def _task(self, task_id: str) -> TaskBoardTask:
        task = next((item for item in self.tasks if item.id == task_id), None)
        if task is None:
            raise ValueError("TaskBoard task is unavailable")
        return task


def create_task_board(
    arguments: dict[str, object],
    user_text: str,
    depth: int,
    *,
    source: str = "planner",
    dispatch_call_id: str | None = None,
    resume_plan: dict[str, object] | None = None,
    max_tasks: int = _MAX_CHILDREN,
    max_parallel: int = _MAX_PARALLEL,
) -> TaskBoard:
    if depth >= _MAX_DEPTH:
        raise ValueError("subagent recursion depth is exhausted")
    raw_tasks = arguments.get("tasks")
    if not isinstance(raw_tasks, list):
        raise ValueError("subagent dispatch requires one to five tasks")
    task_values = cast(list[object], raw_tasks)
    if not 1 <= max_tasks <= _MAX_CHILDREN or not 1 <= max_parallel <= _MAX_CHILDREN:
        raise ValueError("subagent configured task limit is invalid")
    if not (1 <= len(task_values) <= max_tasks):
        raise ValueError("subagent dispatch exceeds the configured task limit")
    if len(task_values) > _MAX_CHILDREN:
        raise ValueError("subagent dispatch requires one to five tasks")
    tasks = [_task_from_value(value, user_text, index) for index, value in enumerate(task_values)]
    _validate_tasks(tasks)
    if source == "agent_loop" and not dispatch_call_id:
        raise ValueError("agent-loop dispatch requires a stable tool call ID")
    return TaskBoard(
        id=new_id("taskboard"),
        tasks=tasks,
        source=source,
        dispatch_call_id=dispatch_call_id,
        resume_plan=dict(resume_plan or {}),
        max_parallel=max_parallel,
    )


def completed_task_board(value: dict[str, object] | None) -> TaskBoard | None:
    if value is None:
        return None
    try:
        board = TaskBoard.from_dict(value)
    except ValueError:
        return None
    return board if board.all_terminal() else None


def _task_from_value(value: object, user_text: str, index: int) -> TaskBoardTask:
    if not isinstance(value, dict):
        raise ValueError("subagent task is invalid")
    data = cast(dict[str, object], value)
    task_id = _text(data.get("id")) or f"task_{index + 1}"
    provenance = _validated_provenance(data, user_text)
    return TaskBoardTask(
        id=task_id,
        title=_text(data.get("title")) or _required(data, "objective", 191)[:80],
        objective=_required(data, "objective", 8_000),
        kind=_task_kind(data.get("kind")),
        depends_on=_string_tuple(data.get("depends_on")),
        required=_boolean(data.get("required"), True),
        capability_scope=_mapping(data.get("capability_scope")),
        budget=TaskBudget.from_value(data.get("budget")),
        result_schema=bounded_result_schema(
            data.get("result_schema") or data.get("output_schema")
        ),
        tool_hints=_string_tuple(data.get("tool_hints")),
        source_hints=_string_tuple(data.get("source_hints")),
        source_provenance=provenance,
        dedupe_key=_text(data.get("dedupe_key")) or task_id,
    )


def _validated_provenance(data: dict[str, object], user_text: str) -> dict[str, object]:
    if _text(data.get("source_role")) != "latest_user_request":
        raise ValueError("subagent task must cite the latest user request")
    quote = _required(data, "source_quote", 8_000)
    span = _mapping(data.get("source_span"))
    start, end = span.get("start"), span.get("end")
    if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end <= start:
        raise ValueError("subagent task source span is invalid")
    if end > len(user_text) or user_text[start:end] != quote:
        raise ValueError("subagent task source does not match the latest user request")
    return {"source_role": "latest_user_request", "source_quote": quote, "source_span": span}


def _validate_tasks(tasks: list[TaskBoardTask]) -> None:
    ids = {task.id for task in tasks}
    if len(ids) != len(tasks) or len({task.dedupe_key for task in tasks}) != len(tasks):
        raise ValueError("subagent task IDs and dedupe keys must be unique")
    if any(any(dep not in ids or dep == task.id for dep in task.depends_on) for task in tasks):
        raise ValueError("subagent task dependency is invalid")
    if sum(task.budget.timeout_seconds for task in tasks) > _MAX_TIMEOUT:
        raise ValueError("subagent timeout budget exceeds the run limit")
    if sum(task.budget.max_tool_calls for task in tasks) > _MAX_TOOL_CALLS:
        raise ValueError("subagent tool budget exceeds the run limit")
    _assert_acyclic(tasks)


def _assert_acyclic(tasks: list[TaskBoardTask]) -> None:
    graph = {task.id: task.depends_on for task in tasks}
    visiting: set[str] = set()
    visited: set[str] = set()
    for task_id in graph:
        _visit(task_id, graph, visiting, visited)


def _visit(
    node: str, graph: dict[str, tuple[str, ...]], visiting: set[str], visited: set[str]
) -> None:
    if node in visited:
        return
    if node in visiting:
        raise ValueError("subagent task dependencies contain a cycle")
    visiting.add(node)
    for dependency in graph[node]:
        _visit(dependency, graph, visiting, visited)
    visiting.remove(node)
    visited.add(node)


def _required(data: dict[str, object], key: str, limit: int) -> str:
    value = _text(data.get(key))
    if not value or len(value) > limit:
        raise ValueError(f"subagent task {key} is invalid")
    return value


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _task_kind(value: object) -> str:
    kind = _text(value).lower()
    allowed = {
        "general",
        "information_lookup",
        "code_read",
        "code_review",
        "code_change",
        "test",
        "document",
    }
    if kind and kind not in allowed:
        raise ValueError("subagent task kind is invalid")
    return kind or "general"


def _optional_text(value: object) -> str | None:
    return _text(value) or None


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    values = cast(list[object], value)
    return tuple(item.strip() for item in values if isinstance(item, str) and item.strip())


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    raw = cast(dict[object, object], value)
    return {key: item for key, item in raw.items() if isinstance(key, str)}


def _mapping_or_none(value: object) -> dict[str, object] | None:
    return _mapping(cast(object, value)) if isinstance(value, dict) else None


def _positive_int(value: object, default: int) -> int:
    if value is None:
        return default
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError("subagent task budget is invalid")
    return value


def _boolean(value: object, default: bool) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ValueError("subagent task boolean field is invalid")
    return value


def _bounded_parallel(value: object) -> int:
    parsed = _positive_int(value, _MAX_PARALLEL)
    if parsed > _MAX_CHILDREN:
        raise ValueError("subagent parallel limit is invalid")
    return parsed
