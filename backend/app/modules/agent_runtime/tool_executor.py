from __future__ import annotations

import asyncio
from dataclasses import dataclass
from time import monotonic
from typing import cast

from app.modules.agent_runtime.capabilities import CapabilitySession
from app.modules.agent_runtime.capability_repetition import (
    repeated_capability_execute,
    repetition_message,
)
from app.modules.agent_runtime.contracts import ChatMessage, ToolCall, ToolDefinition
from app.modules.agent_runtime.control_plane_replan import control_plane_error_code
from app.modules.agent_runtime.diagnostics import RuntimeDiagnostics
from app.modules.agent_runtime.execution_helpers import apply_controls, tool_result
from app.modules.agent_runtime.knowledge_repetition import (
    KnowledgeRepeatReason,
    knowledge_repetition_message,
    repeated_knowledge_search,
)
from app.modules.agent_runtime.knowledge_retry import exhausted_no_results_retry
from app.modules.agent_runtime.math_runtime import MathRuntimePort
from app.modules.agent_runtime.model_observation import tool_result_message
from app.modules.agent_runtime.observations import ToolObservation, observation_from
from app.modules.agent_runtime.output import emit_waiting_for_action
from app.modules.agent_runtime.pending_action import PendingToolActionPort
from app.modules.agent_runtime.runtime_budget import (
    RuntimeExecutionBudget,
    next_consecutive_tool_errors,
)
from app.modules.agent_runtime.script_runtime import ScriptRuntimePort
from app.modules.agent_runtime.subagent_dispatcher import SubagentDispatcherPort
from app.modules.agent_runtime.time_runtime import TimeRuntimePort
from app.modules.agent_runtime.tool_batches import tool_call_batches
from app.modules.interactions.runtime import RuntimeEventSink, RuntimeRequest
from app.modules.knowledge.runtime import KnowledgeRuntimePort
from app.modules.memory.runtime import MemoryRuntimePort
from app.modules.schedules.runtime import ScheduleRuntimePort


@dataclass(frozen=True)
class ToolExecutionOutcome:
    consecutive_tool_errors: int
    stop_reason: str | None = None
    control_plane_error_code: str | None = None


class RuntimeToolExecutor:
    """Owns the stateful tool-execution portion of one in-process Agent turn."""

    def __init__(
        self,
        *,
        memory_runtime: MemoryRuntimePort | None,
        knowledge_runtime: KnowledgeRuntimePort | None,
        schedule_runtime: ScheduleRuntimePort | None,
        time_runtime: TimeRuntimePort,
        math_runtime: MathRuntimePort,
        script_runtime: ScriptRuntimePort | None,
        subagent_dispatcher: SubagentDispatcherPort | None,
        pending_actions: PendingToolActionPort | None,
        max_parallel_tool_calls: int,
        capability_exact_repeat_limit: int,
        capability_similar_repeat_limit: int,
        capability_similarity_threshold: float,
    ) -> None:
        self._memory_runtime = memory_runtime
        self._knowledge_runtime = knowledge_runtime
        self._schedule_runtime = schedule_runtime
        self._time_runtime = time_runtime
        self._math_runtime = math_runtime
        self._script_runtime = script_runtime
        self._subagent_dispatcher = subagent_dispatcher
        self._pending_actions = pending_actions
        self._max_parallel_tool_calls = max_parallel_tool_calls
        self._capability_exact_repeat_limit = capability_exact_repeat_limit
        self._capability_similar_repeat_limit = capability_similar_repeat_limit
        self._capability_similarity_threshold = capability_similarity_threshold

    async def execute_batches(
        self,
        request: RuntimeRequest,
        events: RuntimeEventSink,
        messages: list[ChatMessage],
        calls: tuple[ToolCall, ...],
        capabilities: CapabilitySession,
        tools: tuple[ToolDefinition, ...],
        todos: list[dict[str, str]],
        capability_execute_history: list[dict[str, object]],
        observations: list[ToolObservation],
        budget: RuntimeExecutionBudget,
        consecutive_tool_errors: int,
        diagnostics: RuntimeDiagnostics | None = None,
    ) -> ToolExecutionOutcome:
        available = {item.name: item for item in tools}
        preflight_rejections = self._preflight_rejections(
            calls, available, capability_execute_history, messages
        )
        for batch in tool_call_batches(
            calls,
            max_parallel_calls=self._max_parallel_tool_calls,
            is_parallel_safe=capabilities.is_parallel_safe_call,
        ):
            if await apply_controls(request, events, messages):
                return ToolExecutionOutcome(consecutive_tool_errors, "control")
            results = await self._run_batch(
                request,
                events,
                messages,
                batch,
                capabilities,
                todos,
                preflight_rejections,
                diagnostics,
            )
            outcome = self._record_results(
                messages,
                batch,
                results,
                observations,
                budget,
                consecutive_tool_errors,
            )
            if outcome.stop_reason or outcome.control_plane_error_code:
                return outcome
            consecutive_tool_errors = outcome.consecutive_tool_errors
        return ToolExecutionOutcome(consecutive_tool_errors)

    async def _run_batch(
        self,
        request: RuntimeRequest,
        events: RuntimeEventSink,
        messages: list[ChatMessage],
        calls: tuple[ToolCall, ...],
        capabilities: CapabilitySession,
        todos: list[dict[str, str]],
        preflight_rejections: dict[str, dict[str, object]],
        diagnostics: RuntimeDiagnostics | None,
    ) -> tuple[dict[str, object], ...]:
        if len(calls) == 1:
            return (
                await self._run_tool(
                    request,
                    events,
                    messages,
                    calls[0],
                    capabilities,
                    todos,
                    preflight_rejections.get(calls[0].id),
                    diagnostics,
                ),
            )
        return tuple(
            await asyncio.gather(
                *(
                    self._run_tool(
                        request,
                        events,
                        messages,
                        call,
                        capabilities,
                        todos,
                        preflight_rejections.get(call.id),
                        diagnostics,
                    )
                    for call in calls
                )
            )
        )

    def _record_results(
        self,
        messages: list[ChatMessage],
        calls: tuple[ToolCall, ...],
        results: tuple[dict[str, object], ...],
        observations: list[ToolObservation],
        budget: RuntimeExecutionBudget,
        errors: int,
    ) -> ToolExecutionOutcome:
        for call, result in zip(calls, results, strict=True):
            observations.append(observation_from(call, result))
            messages.append(
                ChatMessage(
                    role="tool",
                    content=tool_result_message(result),
                    name=call.name,
                    tool_call_id=call.id,
                )
            )
            if result.get("status") == "waiting_subagents":
                return ToolExecutionOutcome(errors, "waiting_subagents")
            if result.get("status") == "waiting_approval":
                return ToolExecutionOutcome(errors, "waiting_approval")
            errors = next_consecutive_tool_errors(errors, result)
            if code := control_plane_error_code(call, result):
                return ToolExecutionOutcome(errors, control_plane_error_code=code)
            if errors >= budget.max_consecutive_tool_errors:
                return ToolExecutionOutcome(errors, "max_consecutive_tool_errors_exceeded")
        return ToolExecutionOutcome(errors)

    async def _run_tool(
        self,
        request: RuntimeRequest,
        events: RuntimeEventSink,
        messages: list[ChatMessage],
        call: ToolCall,
        capabilities: CapabilitySession,
        todos: list[dict[str, str]],
        repetition_rejection: dict[str, object] | None,
        diagnostics: RuntimeDiagnostics | None,
    ) -> dict[str, object]:
        await events.append(
            tenant_id=request.tenant_id,
            interaction_id=request.interaction_id,
            request_id=request.request_id,
            event_type="ai.tool.started",
            data={"tool_call_id": call.id, "name": call.name},
        )
        sink = diagnostics or RuntimeDiagnostics(request, events)
        await sink.tool_call(call)
        started = monotonic()
        result: dict[str, object] = repetition_rejection or await self._tool_result(
            call, capabilities, request, events, todos, messages
        )
        duration_ms = (monotonic() - started) * 1_000
        if result.get("status") == "approval_required":
            if self._pending_actions is None:
                result = {
                    "status": "rejected",
                    "code": "MCP_APPROVAL_UNAVAILABLE",
                    "message": "Approval is unavailable for this interaction.",
                }
            else:
                result = await self._pending_actions.prepare(request, call, result, messages)
                await emit_waiting_for_action(request, events, result)
        await events.append(
            tenant_id=request.tenant_id,
            interaction_id=request.interaction_id,
            request_id=request.request_id,
            event_type="ai.tool.completed",
            data={"tool_call_id": call.id, "name": call.name, "status": result.get("status")},
        )
        await sink.tool_result(call, result, duration_ms=duration_ms)
        return result

    async def _tool_result(
        self,
        call: ToolCall,
        capabilities: CapabilitySession,
        request: RuntimeRequest,
        events: RuntimeEventSink,
        todos: list[dict[str, str]],
        messages: list[ChatMessage],
    ) -> dict[str, object]:
        if rejection := exhausted_no_results_retry(messages, call):
            return rejection
        return await tool_result(
            call,
            capabilities,
            self._memory_runtime,
            self._knowledge_runtime,
            self._schedule_runtime,
            self._time_runtime,
            self._math_runtime,
            self._script_runtime,
            self._subagent_dispatcher,
            request,
            events,
            todos,
            messages,
        )

    def _repeat_reason(
        self,
        call: ToolCall,
        history: list[dict[str, object]],
        messages: list[ChatMessage],
        *,
        exclude_call_ids: frozenset[str],
    ) -> str | None:
        if call.name == "knowledge_search":
            return repeated_knowledge_search(
                messages,
                call,
                exclude_call_ids=exclude_call_ids,
                exact_limit=self._capability_exact_repeat_limit,
                similar_limit=self._capability_similar_repeat_limit,
                similarity_threshold=self._capability_similarity_threshold,
            )
        if call.name != "capability_execute":
            return None
        reason = repeated_capability_execute(
            history,
            call.arguments,
            exact_limit=self._capability_exact_repeat_limit,
            similar_limit=self._capability_similar_repeat_limit,
            similarity_threshold=self._capability_similarity_threshold,
        )
        if reason is None:
            history.append(call.arguments)
        return reason

    def _preflight_rejections(
        self,
        calls: tuple[ToolCall, ...],
        available: dict[str, ToolDefinition],
        history: list[dict[str, object]],
        messages: list[ChatMessage],
    ) -> dict[str, dict[str, object]]:
        rejections: dict[str, dict[str, object]] = {}
        exclude_call_ids = frozenset(call.id for call in calls)
        for call in calls:
            definition = available.get(call.name)
            if definition is None:
                rejections[call.id] = {"status": "rejected", "code": "TOOL_NOT_AVAILABLE"}
            elif not definition.accepts_arguments(_arguments_for_validation(call)):
                rejections[call.id] = {
                    "status": "rejected",
                    "code": "TOOL_ARGUMENTS_INVALID",
                    "message": "Tool arguments do not match the declared schema.",
                }
            elif reason := self._repeat_reason(
                call, history, messages, exclude_call_ids=exclude_call_ids
            ):
                if call.name == "knowledge_search":
                    rejections[call.id] = {
                        "status": "rejected",
                        "code": "KNOWLEDGE_SEARCH_REPEAT_BLOCKED",
                        "message": knowledge_repetition_message(
                            cast(KnowledgeRepeatReason, reason)
                        ),
                    }
                else:
                    rejections[call.id] = {
                        "status": "rejected",
                        "code": "CAPABILITY_EXECUTION_REPEAT_BLOCKED",
                        "message": repetition_message(reason),
                    }
        return rejections


def _arguments_for_validation(call: ToolCall) -> dict[str, object]:
    if call.name not in {"capability_search", "capability_execute"}:
        return call.arguments
    legacy_id = call.arguments.get("skill_id")
    if "capability_id" in call.arguments or not isinstance(legacy_id, str):
        return call.arguments
    return {
        **{key: value for key, value in call.arguments.items() if key != "skill_id"},
        "capability_id": legacy_id,
    }
