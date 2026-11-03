from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic

from app.core.agent_runtime import AgentRuntimeProfile
from app.modules.agent_runtime.contracts import AgentModelPort, ChatMessage, ModelProviderError
from app.modules.agent_runtime.diagnostics import RuntimeDiagnostics
from app.modules.agent_runtime.execution_helpers import apply_controls
from app.modules.agent_runtime.final_response import FinalResponseProtocolError
from app.modules.agent_runtime.finalization_checkpoint import (
    FinalizationCheckpoint,
    FinalizationCheckpointPort,
    VolatileFinalizationCheckpointStore,
)
from app.modules.agent_runtime.live_stream import can_publish_thinking, should_flush
from app.modules.agent_runtime.model_retry import stream_with_retry
from app.modules.agent_runtime.output import (
    emit_completed,
    emit_delta,
    emit_thinking_completed,
    emit_thinking_delta,
    reset_output,
    thinking_id,
)
from app.modules.agent_runtime.prompt_composer import with_finalizing_instruction
from app.modules.interactions.runtime import RuntimeEventSink, RuntimeRequest


class FinalRenderProviderError(ModelProviderError):
    """A provider failure whose terminal event must retain the checkpoint output id."""

    output_id: str

    def __init__(self, error: ModelProviderError, output_id: str) -> None:
        super().__init__(str(error), retryable=error.retryable)
        self.output_id = output_id


class FinalRenderProtocolError(FinalResponseProtocolError):
    """A final-render contract violation whose terminal event has a stable output id."""

    output_id: str

    def __init__(self, message: str, output_id: str) -> None:
        super().__init__(message)
        self.output_id = output_id


def _string_parts() -> list[str]:
    return []


@dataclass
class _RenderStreamState:
    content: list[str] = field(default_factory=_string_parts)
    pending: list[str] = field(default_factory=_string_parts)
    thinking: list[str] = field(default_factory=_string_parts)
    pending_thinking: list[str] = field(default_factory=_string_parts)
    delta_index: int = 0
    thinking_delta_index: int = 0
    first_provider_elapsed_ms: float | None = None
    last_flush_at: float = field(default_factory=monotonic)
    last_thinking_flush_at: float = field(default_factory=monotonic)
    output_emitted: bool = False
    thinking_emitted: bool = False
    value_thinking_id: str = ""


class FinalResponseRenderer:
    """Streams the only user-visible final answer after the agent signals completion."""

    def __init__(
        self,
        model: AgentModelPort,
        checkpoints: FinalizationCheckpointPort | None = None,
        *,
        max_retries: int,
    ) -> None:
        self._model = model
        self._checkpoints = checkpoints or VolatileFinalizationCheckpointStore()
        self._max_retries = max_retries

    async def render_new(
        self,
        request: RuntimeRequest,
        events: RuntimeEventSink,
        profile: AgentRuntimeProfile,
        messages: tuple[ChatMessage, ...],
        diagnostics: RuntimeDiagnostics | None,
        *,
        terminal_status: str = "completed",
        completion_data: dict[str, object] | None = None,
    ) -> None:
        checkpoint = await self._checkpoints.prepare(
            request,
            with_finalizing_instruction(messages),
            terminal_status=terminal_status,
            completion_data=completion_data or {},
        )
        await self._stream(request, events, profile, checkpoint, diagnostics)

    async def resume_if_pending(
        self,
        request: RuntimeRequest,
        events: RuntimeEventSink,
        profile: AgentRuntimeProfile,
        diagnostics: RuntimeDiagnostics | None,
    ) -> bool:
        checkpoint = await self._checkpoints.resume(request)
        if checkpoint is None:
            return False
        await self.resume_checkpoint(request, events, profile, checkpoint, diagnostics)
        return True

    async def resume_checkpoint(
        self,
        request: RuntimeRequest,
        events: RuntimeEventSink,
        profile: AgentRuntimeProfile,
        checkpoint: FinalizationCheckpoint,
        diagnostics: RuntimeDiagnostics | None,
    ) -> None:
        if checkpoint.delivery_mode != "render":
            raise ValueError("Final renderer received a candidate checkpoint")
        await self._stream(request, events, profile, checkpoint, diagnostics)

    async def _stream(
        self,
        request: RuntimeRequest,
        events: RuntimeEventSink,
        profile: AgentRuntimeProfile,
        checkpoint: FinalizationCheckpoint,
        diagnostics: RuntimeDiagnostics | None,
    ) -> None:
        if checkpoint.reset_output:
            await reset_output(
                request,
                events,
                value_output_id=checkpoint.output_id,
                reason="final_render_recovered",
            )
        if await self._restart_for_controls(
            request,
            events,
            profile,
            checkpoint,
            diagnostics,
            reset_output=False,
        ):
            return
        try:
            answer = await self._collect_content(request, events, profile, checkpoint, diagnostics)
        except ModelProviderError as error:
            raise FinalRenderProviderError(error, checkpoint.output_id) from error
        if answer is None:
            return
        if not answer.strip():
            raise FinalRenderProtocolError(
                "final renderer returned an empty answer", checkpoint.output_id
            )
        await emit_completed(
            request,
            events,
            answer,
            value_output_id=checkpoint.output_id,
            runtime_status=checkpoint.terminal_status,
            terminal_status=checkpoint.terminal_status,
            extra=checkpoint.completion_data,
        )
        await self._checkpoints.mark_completed(request)
        if diagnostics is not None:
            await diagnostics.milestone("run_completed", phase="final_renderer")

    async def _collect_content(
        self,
        request: RuntimeRequest,
        events: RuntimeEventSink,
        profile: AgentRuntimeProfile,
        checkpoint: FinalizationCheckpoint,
        diagnostics: RuntimeDiagnostics | None,
    ) -> str | None:
        state = _RenderStreamState(
            value_thinking_id=thinking_id(request, turn=0),
        )
        publish_thinking = can_publish_thinking(request, profile.llm)
        async for delta in stream_with_retry(
            self._model,
            profile.llm,
            checkpoint.messages,
            (),
            max_retries=self._max_retries,
            diagnostics=diagnostics,
            diagnostic_phase="final_renderer",
        ):
            if delta.tool_call_deltas:
                raise FinalRenderProtocolError(
                    "final renderer must not call tools", checkpoint.output_id
                )
            if delta.reasoning_content_delta and publish_thinking:
                await self._append_thinking(request, events, state, delta.reasoning_content_delta)
            if not delta.content_delta:
                continue
            await self._append_content(
                request, events, checkpoint, diagnostics, state, delta.content_delta
            )
            if await self._restart_for_controls(
                request,
                events,
                profile,
                checkpoint,
                diagnostics,
                reset_output=state.output_emitted,
            ):
                return None
        if state.pending_thinking and publish_thinking:
            await _emit_pending_thinking(
                request, events, state.pending_thinking, state.thinking_delta_index, state
            )
        if state.thinking_emitted and publish_thinking:
            await emit_thinking_completed(
                request,
                events,
                "".join(state.thinking),
                value_thinking_id=state.value_thinking_id,
            )
        if state.pending:
            await _emit_pending(
                request,
                events,
                state.pending,
                state.delta_index,
                checkpoint.output_id,
            )
        return "".join(state.content)

    async def _append_thinking(
        self,
        request: RuntimeRequest,
        events: RuntimeEventSink,
        state: _RenderStreamState,
        reasoning_delta: str,
    ) -> None:
        state.thinking.append(reasoning_delta)
        state.pending_thinking.append(reasoning_delta)
        if state.thinking_delta_index != 0 and not should_flush(
            state.pending_thinking, state.last_thinking_flush_at
        ):
            return
        await _emit_pending_thinking(
            request, events, state.pending_thinking, state.thinking_delta_index, state
        )

    async def _append_content(
        self,
        request: RuntimeRequest,
        events: RuntimeEventSink,
        checkpoint: FinalizationCheckpoint,
        diagnostics: RuntimeDiagnostics | None,
        state: _RenderStreamState,
        content_delta: str,
    ) -> None:
        if state.first_provider_elapsed_ms is None and diagnostics is not None:
            state.first_provider_elapsed_ms = diagnostics.elapsed_ms()
        state.content.append(content_delta)
        state.pending.append(content_delta)
        if state.delta_index != 0 and not should_flush(state.pending, state.last_flush_at):
            return
        first_public_delta = state.delta_index == 0
        await _emit_pending(
            request,
            events,
            state.pending,
            state.delta_index,
            checkpoint.output_id,
        )
        state.output_emitted = True
        if diagnostics is not None and first_public_delta:
            await diagnostics.milestone(
                "public_first_delta",
                phase="final_renderer",
                provider_elapsed_ms=state.first_provider_elapsed_ms,
            )
        state.delta_index += 1
        state.last_flush_at = monotonic()

    async def _restart_for_controls(
        self,
        request: RuntimeRequest,
        events: RuntimeEventSink,
        profile: AgentRuntimeProfile,
        checkpoint: FinalizationCheckpoint,
        diagnostics: RuntimeDiagnostics | None,
        *,
        reset_output: bool,
    ) -> bool:
        next_checkpoint = await self._checkpoint_after_controls(
            request, events, checkpoint, reset_output=reset_output
        )
        if next_checkpoint is None:
            return True
        if next_checkpoint is checkpoint:
            return False
        await self._stream(request, events, profile, next_checkpoint, diagnostics)
        return True

    async def _checkpoint_after_controls(
        self,
        request: RuntimeRequest,
        events: RuntimeEventSink,
        checkpoint: FinalizationCheckpoint,
        *,
        reset_output: bool,
    ) -> FinalizationCheckpoint | None:
        messages = list(checkpoint.messages)
        if await apply_controls(
            request,
            events,
            messages,
            value_output_id=checkpoint.output_id,
        ):
            return None
        if len(messages) == len(checkpoint.messages):
            return checkpoint
        return await self._checkpoints.restart(
            request,
            tuple(messages),
            reset_output=reset_output,
        )


async def _emit_pending_thinking(
    request: RuntimeRequest,
    events: RuntimeEventSink,
    pending: list[str],
    delta_index: int,
    state: _RenderStreamState,
) -> None:
    value = "".join(pending)
    pending.clear()
    if not value:
        return
    await emit_thinking_delta(
        request,
        events,
        value,
        delta_index,
        value_thinking_id=state.value_thinking_id,
    )
    state.thinking_emitted = True
    state.thinking_delta_index += 1
    state.last_thinking_flush_at = monotonic()


async def _emit_pending(
    request: RuntimeRequest,
    events: RuntimeEventSink,
    pending: list[str],
    delta_index: int,
    output_id: str,
) -> None:
    value = "".join(pending)
    pending.clear()
    await emit_delta(
        request,
        events,
        value,
        delta_index,
        value_output_id=output_id,
    )
