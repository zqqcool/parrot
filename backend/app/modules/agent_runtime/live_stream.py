from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic

from app.core.agent_runtime import RuntimeLlmProfile
from app.modules.agent_runtime.diagnostics import RuntimeDiagnostics
from app.modules.agent_runtime.output import (
    emit_completed,
    emit_delta,
    emit_thinking_completed,
    emit_thinking_delta,
    output_id,
    reset_output,
    thinking_id,
)
from app.modules.interactions.runtime import RuntimeEventSink, RuntimeRequest


def can_publish_thinking(request: RuntimeRequest, llm: RuntimeLlmProfile) -> bool:
    """Root WebSocket visitors may see thinking when the agent LLM enables it."""

    return (
        llm.thinking_enabled
        and request.entry_type == "websocket"
        and request.runtime_depth == 0
        and request.parent_interaction_id is None
    )


def should_flush(pending: list[str], last_flush_at: float) -> bool:
    return sum(len(item) for item in pending) >= 96 or monotonic() - last_flush_at >= 0.05


def _string_parts() -> list[str]:
    return []


@dataclass
class LiveTurnPublisher:
    """Speculatively streams answer tokens and optionally thinking for one model turn.

    Content is public as soon as provider content deltas arrive. If the turn later
    produces tool calls or fails the completion gate, public answer output is reset.
    Thinking stays visible across tool rounds as process, not as the final answer.
    """

    request: RuntimeRequest
    events: RuntimeEventSink
    diagnostics: RuntimeDiagnostics | None
    thinking_enabled: bool
    turn: int
    speculate_content: bool = True
    value_output_id: str = ""
    value_thinking_id: str = ""
    content_parts: list[str] = field(default_factory=_string_parts)
    pending_content: list[str] = field(default_factory=_string_parts)
    thinking_parts: list[str] = field(default_factory=_string_parts)
    pending_thinking: list[str] = field(default_factory=_string_parts)
    content_delta_index: int = 0
    thinking_delta_index: int = 0
    content_emitted: bool = False
    thinking_emitted: bool = False
    tool_calls_seen: bool = False
    abandoned: bool = False
    finalized: bool = False
    last_content_flush_at: float = field(default_factory=monotonic)
    last_thinking_flush_at: float = field(default_factory=monotonic)
    first_provider_content_at: float | None = None

    def __post_init__(self) -> None:
        if not self.value_output_id:
            self.value_output_id = output_id(self.request)
        if not self.value_thinking_id:
            self.value_thinking_id = thinking_id(self.request, turn=self.turn)

    async def on_reasoning_delta(self, delta: str) -> None:
        if not self.thinking_enabled or not delta or self.finalized:
            return
        self.thinking_parts.append(delta)
        self.pending_thinking.append(delta)
        if self.thinking_delta_index != 0 and not should_flush(
            self.pending_thinking, self.last_thinking_flush_at
        ):
            return
        await self._flush_thinking()

    async def on_content_delta(self, delta: str) -> None:
        if not delta or self.tool_calls_seen or self.abandoned or self.finalized:
            return
        if self.first_provider_content_at is None and self.diagnostics is not None:
            self.first_provider_content_at = self.diagnostics.elapsed_ms()
        self.content_parts.append(delta)
        if not self.speculate_content:
            return
        self.pending_content.append(delta)
        if self.content_delta_index != 0 and not should_flush(
            self.pending_content, self.last_content_flush_at
        ):
            return
        await self._flush_content()

    async def on_tool_call_delta(self) -> None:
        self.tool_calls_seen = True
        await self.abandon_content(reason="tool_calls")

    async def finish_thinking(self) -> None:
        if not self.thinking_enabled or self.finalized:
            return
        if self.pending_thinking:
            await self._flush_thinking()
        if not self.thinking_emitted:
            return
        await emit_thinking_completed(
            self.request,
            self.events,
            "".join(self.thinking_parts),
            value_thinking_id=self.value_thinking_id,
        )

    async def abandon_content(self, *, reason: str) -> None:
        if self.abandoned or self.finalized:
            return
        if self.pending_content:
            self.pending_content.clear()
        if not self.content_emitted:
            self.abandoned = True
            self.content_parts.clear()
            return
        await reset_output(
            self.request,
            self.events,
            value_output_id=self.value_output_id,
            reason=reason,
        )
        self.content_emitted = False
        self.content_parts.clear()
        self.content_delta_index = 0
        self.abandoned = True

    async def finalize(
        self,
        content: str,
        *,
        terminal_status: str = "completed",
        completion_data: dict[str, object] | None = None,
    ) -> None:
        if self.finalized:
            return
        if self.pending_content and not self.tool_calls_seen and not self.abandoned:
            await self._flush_content()
        await emit_completed(
            self.request,
            self.events,
            content,
            value_output_id=self.value_output_id,
            runtime_status=terminal_status,
            terminal_status=terminal_status,
            extra=completion_data,
        )
        self.finalized = True
        if self.diagnostics is not None:
            await self.diagnostics.milestone("run_completed", phase="agent_loop")

    async def _flush_content(self) -> None:
        value = "".join(self.pending_content)
        self.pending_content.clear()
        if not value:
            return
        first_public = self.content_delta_index == 0
        await emit_delta(
            self.request,
            self.events,
            value,
            self.content_delta_index,
            value_output_id=self.value_output_id,
        )
        self.content_emitted = True
        if self.diagnostics is not None and first_public:
            await self.diagnostics.milestone(
                "public_first_delta",
                phase="agent_loop",
                provider_elapsed_ms=self.first_provider_content_at,
            )
        self.content_delta_index += 1
        self.last_content_flush_at = monotonic()

    async def _flush_thinking(self) -> None:
        value = "".join(self.pending_thinking)
        self.pending_thinking.clear()
        if not value:
            return
        await emit_thinking_delta(
            self.request,
            self.events,
            value,
            self.thinking_delta_index,
            value_thinking_id=self.value_thinking_id,
        )
        self.thinking_emitted = True
        self.thinking_delta_index += 1
        self.last_thinking_flush_at = monotonic()
