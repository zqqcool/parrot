from __future__ import annotations

from app.core.agent_runtime import AgentRuntimeProfile
from app.modules.agent_runtime.contracts import ChatMessage
from app.modules.agent_runtime.diagnostics import RuntimeDiagnostics
from app.modules.agent_runtime.final_renderer import FinalResponseRenderer
from app.modules.agent_runtime.runtime_budget import RuntimeExecutionBudget
from app.modules.interactions.runtime import RuntimeEventSink, RuntimeRequest


async def emit_budget_partial(
    renderer: FinalResponseRenderer,
    profile: AgentRuntimeProfile,
    messages: list[ChatMessage],
    request: RuntimeRequest,
    events: RuntimeEventSink,
    budget: RuntimeExecutionBudget,
    reason: str,
    diagnostics: RuntimeDiagnostics | None = None,
) -> None:
    await renderer.render_new(
        request,
        events,
        profile,
        tuple(messages),
        diagnostics,
        terminal_status="partial",
        completion_data={
            "budget_exhausted": True,
            "budget_reason": reason,
            "budget": {
                "timeout_seconds": budget.timeout_seconds,
                "max_tool_rounds": budget.max_tool_rounds,
                "max_tool_calls": budget.max_tool_calls,
                "max_consecutive_tool_errors": budget.max_consecutive_tool_errors,
            },
        },
    )
