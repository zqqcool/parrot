from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from app.modules.interactions.runtime import RuntimeRequest


@dataclass(frozen=True)
class RuntimeExecutionBudget:
    timeout_seconds: int
    max_tool_rounds: int
    max_tool_calls: int
    max_consecutive_tool_errors: int


def execution_budget(
    request: RuntimeRequest,
    *,
    timeout_seconds: int,
    max_tool_rounds: int,
    max_tool_calls: int,
    max_consecutive_tool_errors: int,
) -> RuntimeExecutionBudget:
    task = request.subagent_task or {}
    raw = task.get("budget")
    raw_budget = cast(dict[str, object], raw) if isinstance(raw, dict) else {}
    return RuntimeExecutionBudget(
        timeout_seconds=_limited(raw_budget.get("timeout_seconds"), timeout_seconds),
        max_tool_rounds=max_tool_rounds,
        max_tool_calls=_limited(raw_budget.get("max_tool_calls"), max_tool_calls),
        max_consecutive_tool_errors=max_consecutive_tool_errors,
    )


def _limited(value: object, ceiling: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        return ceiling
    return min(value, ceiling)


def tool_budget_reason(
    round_number: int, tool_call_count: int, budget: RuntimeExecutionBudget
) -> str | None:
    if round_number == budget.max_tool_rounds:
        return "max_tool_rounds_exceeded"
    if tool_call_count > budget.max_tool_calls:
        return "max_tool_calls_exceeded"
    return None


def next_consecutive_tool_errors(current: int, result: dict[str, object]) -> int:
    return current + 1 if result.get("status") in {"failed", "rejected"} else 0
