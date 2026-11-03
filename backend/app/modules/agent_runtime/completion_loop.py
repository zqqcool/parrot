from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.core.agent_runtime import AgentRuntimeProfile
from app.modules.agent_runtime.candidate_output import CandidateResponsePublisher
from app.modules.agent_runtime.capabilities import CapabilitySession
from app.modules.agent_runtime.contracts import (
    AgentModelPort,
    ChatCompletion,
    ChatMessage,
    ToolDefinition,
)
from app.modules.agent_runtime.diagnostics import RuntimeDiagnostics
from app.modules.agent_runtime.execution_helpers import apply_controls, can_request_user_input
from app.modules.agent_runtime.final_renderer import FinalResponseRenderer
from app.modules.agent_runtime.final_response import (
    FinalResponseProtocolError,
    terminal_intent_from,
)
from app.modules.agent_runtime.finalization_checkpoint import FinalizationCheckpointPort
from app.modules.agent_runtime.knowledge_output import CitationInventoryHydratorPort
from app.modules.agent_runtime.live_stream import LiveTurnPublisher, can_publish_thinking
from app.modules.agent_runtime.observations import ToolObservation
from app.modules.agent_runtime.output import emit_completed, emit_waiting_for_user
from app.modules.agent_runtime.planner import AgentPlan
from app.modules.agent_runtime.runtime_budget import RuntimeExecutionBudget
from app.modules.agent_runtime.streaming_output import stream_completion
from app.modules.agent_runtime.terminal_delivery import deliver_terminal_output
from app.modules.agent_runtime.terminal_policy import (
    can_speculate_terminal_content,
    partial_message,
    terminal_candidate_decision,
    terminal_repair_instruction,
)
from app.modules.agent_runtime.tool_executor import RuntimeToolExecutor
from app.modules.agent_runtime.tool_rounds import ReplanResult, ToolLoopState, execute_tool_round
from app.modules.interactions.runtime import RuntimeEventSink, RuntimeRequest

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
class _TerminalLoopState:
    finalization_replans: int
    stop: bool


class AgentCompletionLoop:
    def __init__(
        self,
        model: AgentModelPort,
        executor: RuntimeToolExecutor,
        renderer: FinalResponseRenderer,
        checkpoints: FinalizationCheckpointPort,
        replan_tools: ReplanTools,
        *,
        max_model_retries: int,
        max_finalization_replans: int,
        max_control_plane_replans: int,
        citation_hydrator: CitationInventoryHydratorPort | None = None,
    ) -> None:
        self._model = model
        self._executor = executor
        self._renderer = renderer
        self._checkpoints = checkpoints
        self._candidate_publisher = CandidateResponsePublisher(checkpoints)
        self._replan_tools = replan_tools
        self._max_model_retries = max_model_retries
        self._max_finalization_replans = max_finalization_replans
        self._max_control_plane_replans = max_control_plane_replans
        self._citation_hydrator = citation_hydrator

    async def resume(
        self,
        request: RuntimeRequest,
        events: RuntimeEventSink,
        profile: AgentRuntimeProfile,
        diagnostics: RuntimeDiagnostics,
    ) -> bool:
        checkpoint = await self._checkpoints.resume(request)
        if checkpoint is None:
            return False
        if checkpoint.delivery_mode == "candidate":
            await self._candidate_publisher.publish(request, events, checkpoint)
        else:
            await self._renderer.resume_checkpoint(
                request, events, profile, checkpoint, diagnostics
            )
        return True

    async def run(
        self,
        request: RuntimeRequest,
        events: RuntimeEventSink,
        profile: AgentRuntimeProfile,
        messages: list[ChatMessage],
        capabilities: CapabilitySession,
        tools: tuple[ToolDefinition, ...],
        plan: AgentPlan,
        budget: RuntimeExecutionBudget,
        planner_input: str,
        diagnostics: RuntimeDiagnostics,
    ) -> None:
        state = _LoopState()
        for round_number in range(budget.max_tool_rounds + 1):
            if await apply_controls(request, events, messages):
                return
            live = LiveTurnPublisher(
                request=request,
                events=events,
                diagnostics=diagnostics,
                thinking_enabled=can_publish_thinking(request, profile.llm),
                turn=state.model_turn,
                speculate_content=can_speculate_terminal_content(
                    plan, tuple(state.tool_observations)
                ),
            )
            state.model_turn += 1
            completion = await self._stream_turn(
                profile,
                tuple(messages),
                tools,
                diagnostics,
                live=live,
            )
            await live.finish_thinking()
            terminal_intent = await self._handle_terminal_intent(
                request,
                events,
                profile,
                messages,
                completion,
                plan,
                state.tool_observations,
                state.replans,
                diagnostics,
                live=live,
            )
            if terminal_intent is not None:
                state.replans = terminal_intent.finalization_replans
                if terminal_intent.stop:
                    return
                continue
            if not completion.tool_calls:
                terminal = await self._handle_no_tool_completion(
                    request,
                    events,
                    profile,
                    messages,
                    plan,
                    completion,
                    state.tool_observations,
                    state.replans,
                    diagnostics,
                    live=live,
                )
                state.replans = terminal.finalization_replans
                if terminal.stop:
                    return
                continue
            await live.abandon_content(reason="tool_calls")
            outcome = await execute_tool_round(
                self._executor,
                self._replan_tools,
                request,
                events,
                profile,
                messages,
                completion,
                capabilities,
                tools,
                plan,
                budget,
                planner_input,
                state.todos,
                state.capability_execute_history,
                state.tool_observations,
                round_number,
                state.tool_call_count,
                state.consecutive_tool_errors,
                state.control_plane_replans,
                max_control_plane_replans=self._max_control_plane_replans,
                diagnostics=diagnostics,
                final_renderer=self._renderer,
            )
            tools = outcome.tools
            plan = outcome.plan
            state.update_from(outcome)
            if outcome.stop:
                return

    async def _stream_turn(
        self,
        profile: AgentRuntimeProfile,
        messages: tuple[ChatMessage, ...],
        tools: tuple[ToolDefinition, ...],
        diagnostics: RuntimeDiagnostics,
        *,
        live: LiveTurnPublisher,
    ) -> ChatCompletion:
        return await stream_completion(
            self._model,
            profile.llm,
            messages,
            tools,
            max_retries=self._max_model_retries,
            diagnostics=diagnostics,
            live=live,
        )

    async def _handle_terminal_intent(
        self,
        request: RuntimeRequest,
        events: RuntimeEventSink,
        profile: AgentRuntimeProfile,
        messages: list[ChatMessage],
        completion: ChatCompletion,
        plan: AgentPlan,
        tool_observations: list[ToolObservation],
        finalization_replans: int,
        diagnostics: RuntimeDiagnostics,
        *,
        live: LiveTurnPublisher,
    ) -> _TerminalLoopState | None:
        terminal_intent = terminal_intent_from(completion)
        if terminal_intent is None:
            return None
        await live.abandon_content(reason="terminal_tool")
        if terminal_intent.kind == "ask_user":
            if terminal_intent.question is None:
                raise ValueError("ask_user terminal intent requires a question")
            if not can_request_user_input(request):
                raise FinalResponseProtocolError("ask_user is unavailable for this entry")
            await emit_waiting_for_user(request, events, terminal_intent.question)
            return _TerminalLoopState(finalization_replans, True)
        return await self._handle_final_response_intent(
            request,
            events,
            profile,
            messages,
            plan,
            tool_observations,
            finalization_replans,
            diagnostics,
            content=terminal_intent.content,
            live=live,
        )

    async def _handle_final_response_intent(
        self,
        request: RuntimeRequest,
        events: RuntimeEventSink,
        profile: AgentRuntimeProfile,
        messages: list[ChatMessage],
        plan: AgentPlan,
        tool_observations: list[ToolObservation],
        finalization_replans: int,
        diagnostics: RuntimeDiagnostics,
        *,
        content: str | None = None,
        live: LiveTurnPublisher | None = None,
    ) -> _TerminalLoopState:
        decision = terminal_candidate_decision(
            content or "final_response",
            plan,
            observations=tuple(tool_observations),
            repair_attempts=finalization_replans,
            max_repair_attempts=self._max_finalization_replans,
        )
        if decision.kind != "deliver":
            await diagnostics.completion_decision(
                decision.kind, decision.reason, tuple(tool_observations)
            )
        if decision.kind == "deliver":
            await deliver_terminal_output(
                request,
                events,
                profile,
                messages,
                diagnostics,
                renderer=self._renderer,
                candidate_publisher=self._candidate_publisher,
                checkpoints=self._checkpoints,
                content=content,
                observations=tuple(tool_observations),
                signal_only=content is None,
                live=live,
                citation_hydrator=self._citation_hydrator,
            )
            return _TerminalLoopState(finalization_replans, True)
        if decision.kind == "repair":
            if live is not None:
                await live.abandon_content(reason="completion_repair")
            if decision.reason is None:
                raise ValueError("Terminal repair reason is missing")
            messages.append(
                ChatMessage(role="system", content=terminal_repair_instruction(decision.reason))
            )
            return _TerminalLoopState(finalization_replans + 1, False)
        if live is not None:
            await live.abandon_content(reason="completion_partial")
        if decision.reason is None:
            raise ValueError("Terminal partial reason is missing")
        await emit_completed(
            request,
            events,
            partial_message(decision.reason),
            runtime_status="partial",
            terminal_status="partial",
            extra={"partial_reason": decision.reason},
        )
        return _TerminalLoopState(finalization_replans, True)

    async def _handle_no_tool_completion(
        self,
        request: RuntimeRequest,
        events: RuntimeEventSink,
        profile: AgentRuntimeProfile,
        messages: list[ChatMessage],
        plan: AgentPlan,
        completion: ChatCompletion,
        tool_observations: list[ToolObservation],
        finalization_replans: int,
        diagnostics: RuntimeDiagnostics,
        *,
        live: LiveTurnPublisher,
    ) -> _TerminalLoopState:
        message_count = len(messages)
        if await apply_controls(request, events, messages):
            await live.abandon_content(reason="controls")
            return _TerminalLoopState(finalization_replans, True)
        if len(messages) != message_count:
            await live.abandon_content(reason="controls")
            return _TerminalLoopState(finalization_replans, False)
        content = completion.content or ""
        decision = terminal_candidate_decision(
            content,
            plan,
            observations=tuple(tool_observations),
            repair_attempts=finalization_replans,
            max_repair_attempts=self._max_finalization_replans,
        )
        if decision.kind != "deliver":
            await diagnostics.completion_decision(
                decision.kind, decision.reason, tuple(tool_observations)
            )
        if decision.kind == "deliver":
            await deliver_terminal_output(
                request,
                events,
                profile,
                messages,
                diagnostics,
                renderer=self._renderer,
                candidate_publisher=self._candidate_publisher,
                checkpoints=self._checkpoints,
                content=content,
                observations=tuple(tool_observations),
                signal_only=False,
                live=live,
                citation_hydrator=self._citation_hydrator,
            )
            return _TerminalLoopState(finalization_replans, True)
        if decision.kind == "repair":
            await live.abandon_content(reason="completion_repair")
            if decision.reason is None:
                raise ValueError("Terminal repair reason is missing")
            messages.append(
                ChatMessage(role="system", content=terminal_repair_instruction(decision.reason))
            )
            return _TerminalLoopState(finalization_replans + 1, False)
        await live.abandon_content(reason="completion_partial")
        if decision.reason is None:
            raise ValueError("Terminal partial reason is missing")
        await emit_completed(
            request,
            events,
            partial_message(decision.reason),
            runtime_status="partial",
            terminal_status="partial",
            extra={"partial_reason": decision.reason},
        )
        return _TerminalLoopState(finalization_replans, True)


class _LoopState:
    def __init__(self) -> None:
        self.tool_call_count = 0
        self.consecutive_tool_errors = 0
        self.control_plane_replans = 0
        self.replans = 0
        self.model_turn = 0
        self.todos: list[dict[str, str]] = []
        self.capability_execute_history: list[dict[str, object]] = []
        self.tool_observations: list[ToolObservation] = []

    def update_from(self, outcome: ToolLoopState) -> None:
        self.tool_call_count = outcome.tool_call_count
        self.consecutive_tool_errors = outcome.consecutive_tool_errors
        self.control_plane_replans = outcome.control_plane_replans
