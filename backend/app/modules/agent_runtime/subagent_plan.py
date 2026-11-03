from __future__ import annotations

from typing import cast

from app.modules.agent_runtime.planner import AgentPlan

_CAPABILITY_KINDS = frozenset(
    {"information_lookup", "code_read", "code_review", "code_change", "test", "document"}
)


def synthetic_subagent_plan(task: dict[str, object] | None, *, has_capabilities: bool) -> AgentPlan:
    """Derive a bounded plan from the persisted delegated-task contract."""

    payload = task or {}
    kind = _text(payload.get("kind")) or "general"
    hints = _strings(payload.get("tool_hints")) + _strings(payload.get("source_hints"))
    needs_capability = has_capabilities and (kind in _CAPABILITY_KINDS or bool(hints))
    if not needs_capability:
        return AgentPlan(action="direct_answer", synthetic=True)
    return AgentPlan(
        action="capability_lookup",
        capability_query=_capability_query(kind, hints),
        synthetic=True,
    )


def _capability_query(kind: str, hints: tuple[str, ...]) -> str:
    if kind in {"code_read", "code_review", "code_change", "test"}:
        base = "repository reading, code analysis, code change, or test execution capability"
    elif kind == "document":
        base = "document reading, editing, conversion, or formatting capability"
    else:
        base = "current external information lookup, web search, and source retrieval capability"
    if hints:
        return f"{base}; capability hints: {', '.join(dict.fromkeys(hints[:8]))}"
    return base


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    items = cast(list[object], value)
    return tuple(item.strip() for item in items if isinstance(item, str) and item.strip())


def _text(value: object) -> str:
    return value.strip().lower() if isinstance(value, str) else ""
