from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from app.modules.agent_runtime.contracts import ChatMessage
from app.modules.interactions.runtime import RuntimeRequest

FinalizationDeliveryMode = Literal["render", "candidate"]


@dataclass(frozen=True)
class FinalizationCheckpoint:
    delivery_mode: FinalizationDeliveryMode
    messages: tuple[ChatMessage, ...]
    output_id: str
    terminal_status: str
    completion_data: dict[str, object]
    candidate_content: str | None = None
    candidate_deltas: tuple[str, ...] = ()
    reset_output: bool = False


class FinalizationCheckpointPort(Protocol):
    async def prepare(
        self,
        request: RuntimeRequest,
        messages: tuple[ChatMessage, ...],
        *,
        terminal_status: str,
        completion_data: dict[str, object],
    ) -> FinalizationCheckpoint: ...

    async def prepare_candidate(
        self,
        request: RuntimeRequest,
        content: str,
        deltas: tuple[str, ...],
        *,
        terminal_status: str,
        completion_data: dict[str, object],
    ) -> FinalizationCheckpoint: ...

    async def resume(self, request: RuntimeRequest) -> FinalizationCheckpoint | None: ...

    async def mark_visible(self, request: RuntimeRequest) -> None: ...

    async def restart(
        self,
        request: RuntimeRequest,
        messages: tuple[ChatMessage, ...],
        *,
        reset_output: bool,
    ) -> FinalizationCheckpoint: ...

    async def mark_completed(self, request: RuntimeRequest) -> None: ...


class VolatileFinalizationCheckpointStore(FinalizationCheckpointPort):
    """Test-only fallback; production construction always injects the SQL store."""

    def __init__(self) -> None:
        self._items: dict[str, FinalizationCheckpoint] = {}
        self._visible: set[str] = set()

    async def prepare(
        self,
        request: RuntimeRequest,
        messages: tuple[ChatMessage, ...],
        *,
        terminal_status: str,
        completion_data: dict[str, object],
    ) -> FinalizationCheckpoint:
        item = FinalizationCheckpoint(
            delivery_mode="render",
            messages=messages,
            output_id=request.output_id or f"output_{request.interaction_id}",
            terminal_status=terminal_status,
            completion_data=completion_data,
        )
        self._items[request.interaction_id] = item
        self._visible.add(request.interaction_id)
        return item

    async def prepare_candidate(
        self,
        request: RuntimeRequest,
        content: str,
        deltas: tuple[str, ...],
        *,
        terminal_status: str,
        completion_data: dict[str, object],
    ) -> FinalizationCheckpoint:
        item = candidate_checkpoint(
            request,
            content,
            deltas,
            terminal_status=terminal_status,
            completion_data=completion_data,
        )
        self._items[request.interaction_id] = item
        return item

    async def resume(self, request: RuntimeRequest) -> FinalizationCheckpoint | None:
        item = self._items.get(request.interaction_id)
        if item is None:
            return None
        return FinalizationCheckpoint(
            delivery_mode=item.delivery_mode,
            messages=item.messages,
            output_id=item.output_id,
            terminal_status=item.terminal_status,
            completion_data=item.completion_data,
            candidate_content=item.candidate_content,
            candidate_deltas=item.candidate_deltas,
            reset_output=request.interaction_id in self._visible,
        )

    async def mark_visible(self, request: RuntimeRequest) -> None:
        self._visible.add(request.interaction_id)

    async def restart(
        self,
        request: RuntimeRequest,
        messages: tuple[ChatMessage, ...],
        *,
        reset_output: bool,
    ) -> FinalizationCheckpoint:
        item = self._items.get(request.interaction_id)
        if item is None:
            raise ValueError("Finalization checkpoint is unavailable")
        item = FinalizationCheckpoint(
            delivery_mode=item.delivery_mode,
            messages=messages,
            output_id=item.output_id,
            terminal_status=item.terminal_status,
            completion_data=item.completion_data,
            candidate_content=item.candidate_content,
            candidate_deltas=item.candidate_deltas,
            reset_output=reset_output,
        )
        self._items[request.interaction_id] = item
        if item.delivery_mode == "render":
            self._visible.add(request.interaction_id)
        else:
            self._visible.discard(request.interaction_id)
        return item

    async def mark_completed(self, request: RuntimeRequest) -> None:
        self._items.pop(request.interaction_id, None)
        self._visible.discard(request.interaction_id)


def candidate_checkpoint(
    request: RuntimeRequest,
    content: str,
    deltas: tuple[str, ...],
    *,
    terminal_status: str,
    completion_data: dict[str, object],
) -> FinalizationCheckpoint:
    content, deltas = validate_candidate(content, deltas)
    return FinalizationCheckpoint(
        delivery_mode="candidate",
        messages=(),
        output_id=request.output_id or f"output_{request.interaction_id}",
        terminal_status=terminal_status,
        completion_data=completion_data,
        candidate_content=content,
        candidate_deltas=deltas,
    )


def validate_candidate(content: str, deltas: tuple[str, ...]) -> tuple[str, tuple[str, ...]]:
    if not content.strip() or not deltas or any(not item for item in deltas):
        raise ValueError("Finalization candidate is invalid")
    if "".join(deltas) != content:
        raise ValueError("Finalization candidate deltas do not match content")
    return content, deltas
