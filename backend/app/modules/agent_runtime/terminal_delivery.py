from __future__ import annotations

from typing import Literal

from app.core.agent_runtime import AgentRuntimeProfile
from app.modules.agent_runtime.candidate_output import CandidateResponsePublisher
from app.modules.agent_runtime.contracts import ChatMessage
from app.modules.agent_runtime.diagnostics import RuntimeDiagnostics
from app.modules.agent_runtime.final_renderer import FinalResponseRenderer
from app.modules.agent_runtime.finalization_checkpoint import FinalizationCheckpointPort
from app.modules.agent_runtime.knowledge_output import (
    CitationInventoryHydratorPort,
    KnowledgeCitationInventoryItem,
    assemble_knowledge_output,
    completion_extra,
    hydration_candidates,
    inventory_from_messages,
    merge_inventories,
)
from app.modules.agent_runtime.live_stream import LiveTurnPublisher
from app.modules.agent_runtime.observations import ToolObservation
from app.modules.agent_runtime.subagent_continuation import subagent_terminal_metadata
from app.modules.interactions.runtime import RuntimeEventSink, RuntimeRequest

TerminalDeliveryMode = Literal["candidate", "render", "live"]


def terminal_delivery_mode(
    content: str,
    observations: tuple[ToolObservation, ...] = (),
    *,
    signal_only: bool = False,
    live_streamed: bool = False,
) -> TerminalDeliveryMode:
    """Choose how to publish a terminal answer that already passed the completion gate.

    User-visible prose is authored at most once:
    - Live-streamed answer turns only emit ``ai.output.completed`` (deltas already public).
    - Signal-only ``final_response`` enters Final Renderer for a single authoring stream.
    - Tool-arg ``final_response(content=...)`` remains a one-shot candidate (no rewrite).
    """
    del observations
    if signal_only:
        return "render"
    if live_streamed:
        return "live"
    if content.strip():
        return "candidate"
    return "candidate"


async def deliver_terminal_output(
    request: RuntimeRequest,
    events: RuntimeEventSink,
    profile: AgentRuntimeProfile,
    messages: list[ChatMessage],
    diagnostics: RuntimeDiagnostics,
    *,
    renderer: FinalResponseRenderer,
    candidate_publisher: CandidateResponsePublisher,
    checkpoints: FinalizationCheckpointPort,
    content: str | None,
    observations: tuple[ToolObservation, ...],
    signal_only: bool,
    live: LiveTurnPublisher | None = None,
    citation_hydrator: CitationInventoryHydratorPort | None = None,
) -> TerminalDeliveryMode:
    terminal_status, completion_data = subagent_terminal_metadata(request.task_board)
    inventory = await _terminal_inventory(
        request.tenant_id,
        content or "",
        observations,
        messages,
        citation_hydrator,
    )
    assembled = assemble_knowledge_output(content or "", inventory)
    content = assembled.content
    completion_data = {**completion_data, **completion_extra(assembled)}
    live_streamed = live is not None and live.content_emitted and not live.abandoned
    delivery = terminal_delivery_mode(
        content or "",
        observations,
        signal_only=signal_only,
        live_streamed=live_streamed,
    )
    await diagnostics.completion_decision(f"deliver:{delivery}", None, observations)
    if delivery == "render":
        await renderer.render_new(
            request,
            events,
            profile,
            tuple(messages),
            diagnostics,
            terminal_status=terminal_status,
            completion_data=completion_data,
        )
        return delivery
    if delivery == "live":
        if live is None:
            raise ValueError("Live delivery requires a live turn publisher")
        checkpoint = await checkpoints.prepare_candidate(
            request,
            content or "",
            (content or "",),
            terminal_status=terminal_status,
            completion_data=completion_data,
        )
        await checkpoints.mark_visible(request)
        await live.finalize(
            content or "",
            terminal_status=checkpoint.terminal_status,
            completion_data=checkpoint.completion_data,
        )
        await checkpoints.mark_completed(request)
        return delivery
    await candidate_publisher.publish_new(
        request,
        events,
        content or "",
        terminal_status=terminal_status,
        completion_data=completion_data,
    )
    return delivery


async def _terminal_inventory(
    tenant_id: str,
    content: str,
    observations: tuple[ToolObservation, ...],
    messages: list[ChatMessage],
    citation_hydrator: CitationInventoryHydratorPort | None,
) -> tuple[KnowledgeCitationInventoryItem, ...]:
    observed = tuple(
        item for observation in observations for item in observation.knowledge_citations
    )
    inventory = merge_inventories(observed, inventory_from_messages(messages))
    missing = hydration_candidates(content, inventory)
    if citation_hydrator is None or not missing:
        return inventory
    hydrated = await citation_hydrator.hydrate(tenant_id, missing)
    return merge_inventories(inventory, hydrated)
