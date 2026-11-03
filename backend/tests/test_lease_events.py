from __future__ import annotations

import pytest

from app.modules.agent_runtime.lease_events import LeaseBoundEventSink


class RecordingSink:
    def __init__(self) -> None:
        self.lease_owner: str | None = None

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
        del (
            tenant_id,
            interaction_id,
            request_id,
            event_type,
            data,
            terminal_status,
            runtime_event_sequence,
        )
        self.lease_owner = lease_owner
        return object()

    async def record_trace(
        self,
        *,
        tenant_id: str,
        interaction_id: str,
        trace_type: str,
        data: dict[str, object],
        lease_owner: str | None = None,
    ) -> object:
        del tenant_id, interaction_id, trace_type, data
        self.lease_owner = lease_owner
        return object()


@pytest.mark.asyncio
async def test_lease_bound_sink_supplies_its_claim_owner() -> None:
    sink = RecordingSink()
    events = LeaseBoundEventSink(sink, "worker-a")

    await events.append(
        tenant_id="tenant_test",
        interaction_id="interaction_test",
        request_id="request_test",
        event_type="ai.output.completed",
        data={},
    )

    assert sink.lease_owner == "worker-a"


@pytest.mark.asyncio
async def test_lease_bound_sink_rejects_another_worker_owner() -> None:
    events = LeaseBoundEventSink(RecordingSink(), "worker-a")

    with pytest.raises(ValueError, match="cannot be overridden"):
        await events.append(
            tenant_id="tenant_test",
            interaction_id="interaction_test",
            request_id="request_test",
            event_type="ai.output.completed",
            data={},
            lease_owner="worker-b",
        )


@pytest.mark.asyncio
async def test_lease_bound_sink_fences_diagnostic_traces() -> None:
    sink = RecordingSink()
    events = LeaseBoundEventSink(sink, "worker-a")

    await events.record_trace(
        tenant_id="tenant_test",
        interaction_id="interaction_test",
        trace_type="model.request",
        data={},
    )

    assert sink.lease_owner == "worker-a"
