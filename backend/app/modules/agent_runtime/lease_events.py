from __future__ import annotations

from app.modules.interactions.runtime import RuntimeEventSink


class LeaseBoundEventSink:
    """Fences worker-emitted events to the interaction lease owner that claimed the run."""

    def __init__(self, sink: RuntimeEventSink, owner: str) -> None:
        self._sink = sink
        self._owner = owner

    async def append(
        self,
        *,
        tenant_id: str,
        interaction_id: str,
        request_id: str,
        event_type: str,
        data: dict[str, object],
        terminal_status: str | None = None,
        runtime_event_sequence: int | None = None,
        lease_owner: str | None = None,
    ) -> object:
        if lease_owner not in (None, self._owner):
            raise ValueError("Lease-bound event sink owner cannot be overridden")
        return await self._sink.append(
            tenant_id=tenant_id,
            interaction_id=interaction_id,
            request_id=request_id,
            event_type=event_type,
            data=data,
            terminal_status=terminal_status,
            runtime_event_sequence=runtime_event_sequence,
            lease_owner=self._owner,
        )

    async def record_trace(
        self,
        *,
        tenant_id: str,
        interaction_id: str,
        trace_type: str,
        data: dict[str, object],
        lease_owner: str | None = None,
    ) -> object:
        if lease_owner not in (None, self._owner):
            raise ValueError("Lease-bound event sink owner cannot be overridden")
        return await self._sink.record_trace(
            tenant_id=tenant_id,
            interaction_id=interaction_id,
            trace_type=trace_type,
            data=data,
            lease_owner=self._owner,
        )
