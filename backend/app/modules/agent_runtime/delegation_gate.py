from __future__ import annotations

from app.modules.agent_runtime.planner import AgentPlan
from app.modules.interactions.runtime import RuntimeRequest


def can_dispatch_from_loop(request: RuntimeRequest, plan: AgentPlan) -> bool:
    """Allow one root-only delegation while the loop is gathering evidence."""

    return (
        request.runtime_depth == 0
        and request.entry_type not in {"schedule", "subagent"}
        and request.task_board is None
        and _supports_loop_dispatch(request, plan)
    )


def _supports_loop_dispatch(request: RuntimeRequest, plan: AgentPlan) -> bool:
    del request
    return plan.action in {"agent_loop", "capability_lookup"}
