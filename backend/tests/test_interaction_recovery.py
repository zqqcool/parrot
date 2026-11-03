from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest

from app.infrastructure.db.session import DatabaseManager
from app.modules.interactions.event_store import InteractionEventStore
from app.modules.interactions.models import Interaction


class EventStoreDatabase:
    def __init__(self, session: SimpleNamespace) -> None:
        self._session = session
        self.set_tenant = AsyncMock()

    @asynccontextmanager
    async def session(self):
        yield self._session


@pytest.mark.asyncio
async def test_event_store_discards_already_forwarded_runtime_event() -> None:
    interaction = Interaction(
        id="interaction_test",
        tenant_id="tenant_test",
        agent_id="agent_test",
        actor_type="anonymous",
        actor_id="visitor_test",
        entry_type="text",
        input_type="text",
        runtime_event_sequence=8,
    )
    session = SimpleNamespace(scalar=AsyncMock(return_value=interaction), add=AsyncMock())
    database = EventStoreDatabase(session)

    result = await InteractionEventStore(cast(DatabaseManager, database)).append(
        tenant_id="tenant_test",
        interaction_id="interaction_test",
        request_id="request_test",
        event_type="ai.output.delta",
        data={"delta": "already persisted"},
        runtime_event_sequence=8,
    )

    assert result is None
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_event_store_keeps_waiting_user_input_resumable() -> None:
    interaction = Interaction(
        id="interaction_test",
        tenant_id="tenant_test",
        agent_id="agent_test",
        actor_type="anonymous",
        actor_id="visitor_test",
        entry_type="text",
        input_type="text",
        status="running",
        runtime_recovery_lease_owner="worker_test",
    )
    session = SimpleNamespace(
        scalar=AsyncMock(side_effect=(interaction, 0)),
        add=Mock(),
        flush=AsyncMock(),
    )
    database = EventStoreDatabase(session)

    result = await InteractionEventStore(cast(DatabaseManager, database)).append(
        tenant_id="tenant_test",
        interaction_id="interaction_test",
        request_id="request_test",
        event_type="ai.output.completed",
        data={"runtime_status": "waiting_user_input", "content": "Which release?"},
        terminal_status="waiting_user_input",
    )

    assert result is not None
    assert interaction.status == "waiting_user_input"
    assert interaction.runtime_recovery_lease_owner == "worker_test"


@pytest.mark.asyncio
async def test_event_store_releases_waiting_worker_lease_when_user_resumes() -> None:
    interaction = Interaction(
        id="interaction_test",
        tenant_id="tenant_test",
        agent_id="agent_test",
        actor_type="anonymous",
        actor_id="visitor_test",
        entry_type="websocket",
        input_type="text",
        status="waiting_user_input",
        runtime_recovery_lease_owner="worker_test",
    )
    session = SimpleNamespace(
        scalar=AsyncMock(side_effect=(interaction, 1)),
        add=Mock(),
        flush=AsyncMock(),
    )
    database = EventStoreDatabase(session)

    await InteractionEventStore(cast(DatabaseManager, database)).append(
        tenant_id="tenant_test",
        interaction_id="interaction_test",
        request_id="request_resume",
        event_type="ai.interaction.steer.requested",
        data={"message": "Use the production release."},
        terminal_status="accepted",
    )

    assert interaction.status == "accepted"
    assert interaction.runtime_recovery_lease_owner is None
    assert interaction.runtime_recovery_lease_until is None


@pytest.mark.asyncio
async def test_event_store_keeps_worker_lease_for_post_terminal_diagnostics() -> None:
    interaction = Interaction(
        id="interaction_test",
        tenant_id="tenant_test",
        agent_id="agent_test",
        actor_type="anonymous",
        actor_id="visitor_test",
        entry_type="text",
        input_type="text",
        status="running",
        runtime_recovery_lease_owner="worker_test",
    )
    session = SimpleNamespace(
        scalar=AsyncMock(side_effect=(interaction, 0)),
        add=Mock(),
        flush=AsyncMock(),
    )
    database = EventStoreDatabase(session)

    result = await InteractionEventStore(cast(DatabaseManager, database)).append(
        tenant_id="tenant_test",
        interaction_id="interaction_test",
        request_id="request_test",
        event_type="ai.output.completed",
        data={"runtime_status": "completed", "content": "Done."},
        terminal_status="completed",
        lease_owner="worker_test",
    )

    assert result is not None
    assert interaction.status == "completed"
    assert interaction.runtime_recovery_lease_owner == "worker_test"


@pytest.mark.asyncio
async def test_event_store_clears_lease_for_non_worker_terminal_event() -> None:
    interaction = Interaction(
        id="interaction_test",
        tenant_id="tenant_test",
        agent_id="agent_test",
        actor_type="anonymous",
        actor_id="visitor_test",
        entry_type="text",
        input_type="text",
        status="running",
        runtime_recovery_lease_owner="stale_worker",
    )
    session = SimpleNamespace(
        scalar=AsyncMock(side_effect=(interaction, 0)),
        add=Mock(),
        flush=AsyncMock(),
    )
    database = EventStoreDatabase(session)

    await InteractionEventStore(cast(DatabaseManager, database)).append(
        tenant_id="tenant_test",
        interaction_id="interaction_test",
        request_id="request_test",
        event_type="ai.output.failed",
        data={"runtime_status": "failed"},
        terminal_status="failed",
    )

    assert interaction.status == "failed"
    assert interaction.runtime_recovery_lease_owner is None
