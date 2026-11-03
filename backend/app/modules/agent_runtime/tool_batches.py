from __future__ import annotations

from collections.abc import Callable

from app.modules.agent_runtime.contracts import ToolCall

_PARALLEL_SAFE_TOOLS = frozenset({"time", "math", "knowledge_search"})


def tool_call_batches(
    calls: tuple[ToolCall, ...],
    *,
    max_parallel_calls: int,
    is_parallel_safe: Callable[[ToolCall], bool] | None = None,
) -> tuple[tuple[ToolCall, ...], ...]:
    """Batch pure built-ins and independent knowledge reads; keep stateful barriers serial."""

    batches: list[tuple[ToolCall, ...]] = []
    parallel: list[ToolCall] = []
    for call in calls:
        if call.name in _PARALLEL_SAFE_TOOLS or (
            is_parallel_safe is not None and is_parallel_safe(call)
        ):
            parallel.append(call)
            if len(parallel) == max_parallel_calls:
                batches.append(tuple(parallel))
                parallel = []
            continue
        if parallel:
            batches.append(tuple(parallel))
            parallel = []
        batches.append((call,))
    if parallel:
        batches.append(tuple(parallel))
    return tuple(batches)
