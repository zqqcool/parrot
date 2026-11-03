from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.core.agent_runtime import AgentRuntimeProfile
from app.modules.agent_runtime.budget_finalizer import emit_budget_partial
from app.modules.agent_runtime.capabilities import CapabilitySession
from app.modules.agent_runtime.contracts import (
    ChatCompletion,
    ChatMessage,
    ToolDefinition,
)
from app.modules.agent_runtime.diagnostics import RuntimeDiagnostics
from app.modules.agent_runtime.final_renderer import FinalResponseRenderer
from app.modules.agent_runtime.observations import ToolObservation
from app.modules.agent_runtime.planner import AgentPlan
from app.modules.agent_runtime.runtime_budget import RuntimeExecutionBudget, tool_budget_reason
from app.modules.agent_runtime.tool_executor import RuntimeToolExecutor
from app.modules.interactions.runtime import RuntimeEventSink, RuntimeRequest


@dataclass(frozen=True)
class ReplanResult:
    plan: AgentPlan
    tools: tuple[ToolDefinition, ...]


ReplanTools = Callable[
    [
        RuntimeRequest,
        RuntimeEventSink,
        AgentRuntimeProfile,
        list[ChatMessage],
        str,
        str,
        RuntimeDiagnostics | None,
    ],
    Awaitable[ReplanResult | None],
]


@dataclass(frozen=True)
class ToolLoopState:
    plan: AgentPlan
    tools: tuple[ToolDefinition, ...]
    tool_call_count: int
    consecutive_tool_errors: int
    control_plane_replans: int
    stop: bool


async def execute_tool_round(
    executor: RuntimeToolExecutor,
    replan_tools: ReplanTools,
    request: RuntimeRequest,
    events: RuntimeEventSink,
    profile: AgentRuntimeProfile,
    messages: list[ChatMessage],
    completion: ChatCompletion,
    capabilities: CapabilitySession,
    tools: tuple[ToolDefinition, ...],
    plan: AgentPlan,
    budget: RuntimeExecutionBudget,
    planner_input: str,
    todos: list[dict[str, str]],
    capability_execute_history: list[dict[str, object]],
    tool_observations: list[ToolObservation],
    round_number: int,
    tool_call_count: int,
    consecutive_tool_errors: int,
    control_plane_replans: int,
    *,
    final_renderer: FinalResponseRenderer,
    max_control_plane_replans: int,
    diagnostics: RuntimeDiagnostics | None = None,
) -> ToolLoopState:
    tool_call_count += len(completion.tool_calls)
    messages.append(
        ChatMessage(
            content=completion.content,
            role="assistant",
            tool_calls=completion.tool_calls,
            reasoning_content=completion.reasoning_content,
        )
    )
    if reason := tool_budget_reason(round_number, tool_call_count, budget):
        await _emit_budget_partial(
            final_renderer,
            profile,
            messages,
            request,
            events,
            budget,
            reason,
            diagnostics,
        )
        return ToolLoopState(
            plan, tools, tool_call_count, consecutive_tool_errors, control_plane_replans, True
        )
    outcome = await executor.execute_batches(
        request,
        events,
        messages,
        completion.tool_calls,
        capabilities,
        tools,
        todos,
        capability_execute_history,
        tool_observations,
        budget,
        consecutive_tool_errors,
        diagnostics=diagnostics,
    )
    consecutive_tool_errors = outcome.consecutive_tool_errors
    if outcome.control_plane_error_code and control_plane_replans < max_control_plane_replans:
        control_plane_replans += 1
        replan = await replan_tools(
            request,
            events,
            profile,
            messages,
            planner_input,
            outcome.control_plane_error_code,
            diagnostics,
        )
        if replan is None:
            return ToolLoopState(
                plan,
                tools,
                tool_call_count,
                consecutive_tool_errors,
                control_plane_replans,
                True,
            )
        return ToolLoopState(
            replan.plan,
            replan.tools,
            tool_call_count,
            consecutive_tool_errors,
            control_plane_replans,
            False,
        )
    if outcome.stop_reason == "max_consecutive_tool_errors_exceeded" or (
        outcome.control_plane_error_code
        and consecutive_tool_errors >= budget.max_consecutive_tool_errors
    ):
        await _emit_budget_partial(
            final_renderer,
            profile,
            messages,
            request,
            events,
            budget,
            "max_consecutive_tool_errors_exceeded",
            diagnostics,
        )
        return ToolLoopState(
            plan, tools, tool_call_count, consecutive_tool_errors, control_plane_replans, True
        )
    return ToolLoopState(
        plan,
        tools,
        tool_call_count,
        consecutive_tool_errors,
        control_plane_replans,
        bool(outcome.stop_reason),
    )


async def _emit_budget_partial(
    renderer: FinalResponseRenderer,
    profile: AgentRuntimeProfile,
    messages: list[ChatMessage],
    request: RuntimeRequest,
    events: RuntimeEventSink,
    budget: RuntimeExecutionBudget,
    reason: str,
    diagnostics: RuntimeDiagnostics | None,
) -> None:
    await emit_budget_partial(
        renderer,
        profile,
        messages,
        request,
        events,
        budget,
        reason,
        diagnostics=diagnostics,
    )
