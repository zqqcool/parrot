from __future__ import annotations

from app.modules.agent_runtime.finalization_checkpoint import (
    FinalizationCheckpoint,
    FinalizationCheckpointPort,
)
from app.modules.agent_runtime.output import emit_completed, emit_delta, reset_output
from app.modules.interactions.runtime import RuntimeEventSink, RuntimeRequest


class CandidateResponsePublisher:
    """Publishes a durable terminal candidate without re-invoking the model."""

    def __init__(self, checkpoints: FinalizationCheckpointPort) -> None:
        self._checkpoints = checkpoints

    async def publish_new(
        self,
        request: RuntimeRequest,
        events: RuntimeEventSink,
        content: str,
        *,
        terminal_status: str = "completed",
        completion_data: dict[str, object] | None = None,
    ) -> None:
        # The provider stream has already ended before a candidate is proven terminal.
        # Publish the verified value once instead of replaying buffered provider deltas
        # and presenting a second, artificial stream to the client. Older durable
        # checkpoints may still contain multiple deltas and remain resumable.
        checkpoint = await self._checkpoints.prepare_candidate(
            request,
            content,
            (content,),
            terminal_status=terminal_status,
            completion_data=completion_data or {},
        )
        await self.publish(request, events, checkpoint)

    async def publish(
        self,
        request: RuntimeRequest,
        events: RuntimeEventSink,
        checkpoint: FinalizationCheckpoint,
    ) -> None:
        if checkpoint.delivery_mode != "candidate":
            raise ValueError("Candidate publisher received a renderer checkpoint")
        content = checkpoint.candidate_content
        if content is None:
            raise ValueError("Candidate checkpoint content is missing")
        if checkpoint.reset_output:
            await reset_output(
                request,
                events,
                value_output_id=checkpoint.output_id,
                reason="candidate_output_recovered",
            )
        await self._checkpoints.mark_visible(request)
        for index, delta in enumerate(checkpoint.candidate_deltas):
            await emit_delta(
                request,
                events,
                delta,
                index,
                value_output_id=checkpoint.output_id,
            )
        await emit_completed(
            request,
            events,
            content,
            value_output_id=checkpoint.output_id,
            runtime_status=checkpoint.terminal_status,
            terminal_status=checkpoint.terminal_status,
            extra=checkpoint.completion_data,
        )
        await self._checkpoints.mark_completed(request)
