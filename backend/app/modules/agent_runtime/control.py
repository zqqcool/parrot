from __future__ import annotations

from sqlalchemy import select

from app.infrastructure.db.session import DatabaseManager
from app.modules.interactions.models import InteractionEvent
from app.modules.interactions.runtime import RuntimeControlState, RuntimeRequest

_CONTROL_TYPES = ("ai.interaction.cancel.requested", "ai.interaction.steer.requested")


class InteractionControlReader:
    """Reads durable controls once for one claimed interaction."""

    def __init__(self, database: DatabaseManager) -> None:
        self.database = database
        self._last_sequence = 0

    async def consume(self, request: RuntimeRequest) -> RuntimeControlState:
        after_sequence = max(self._last_sequence, request.control_after_sequence)
        async with self.database.session() as session:
            await self.database.set_tenant(session, request.tenant_id)
            rows = await session.scalars(
                select(InteractionEvent)
                .where(
                    InteractionEvent.tenant_id == request.tenant_id,
                    InteractionEvent.interaction_id == request.interaction_id,
                    InteractionEvent.sequence > after_sequence,
                    InteractionEvent.type.in_(_CONTROL_TYPES),
                )
                .order_by(InteractionEvent.sequence)
            )
            events = tuple(rows)
        if events:
            self._last_sequence = events[-1].sequence
        messages = tuple(
            value
            for event in events
            if event.type == "ai.interaction.steer.requested"
            if isinstance(value := event.data.get("message"), str) and value.strip()
        )
        return RuntimeControlState(
            cancel_requested=any(
                event.type == "ai.interaction.cancel.requested" for event in events
            ),
            steering_messages=messages,
        )
