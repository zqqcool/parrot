from __future__ import annotations

import logging
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import utc_now
from app.core.ids import new_id
from app.infrastructure.db.session import DatabaseManager
from app.modules.interactions.models import (
    ConversationMessage,
    Interaction,
    InteractionDiagnosticTrace,
    InteractionEvent,
)
from app.modules.interactions.schemas import InteractionEventView

logger = logging.getLogger(__name__)
_TERMINAL_STATUSES = frozenset({"completed", "partial", "failed", "cancelled"})


class InteractionEventStore:
    def __init__(
        self,
        database: DatabaseManager,
        notifier: InteractionEventNotifier | None = None,
    ) -> None:
        self.database = database
        self.notifier = notifier

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
    ) -> InteractionEventView | None:
        async with self.database.session() as session:
            await self.database.set_tenant(session, tenant_id)
            # Serialize sequence allocation per interaction. A max(sequence) query alone races
            # when a runtime emits tool and model events concurrently.
            interaction = await session.scalar(
                select(Interaction).where(Interaction.id == interaction_id).with_for_update()
            )
            if interaction is None:
                raise ValueError("interaction does not exist")
            if lease_owner is not None and interaction.runtime_recovery_lease_owner != lease_owner:
                return None
            if interaction.status in _TERMINAL_STATUSES:
                return None
            if (
                runtime_event_sequence is not None
                and runtime_event_sequence <= interaction.runtime_event_sequence
            ):
                return None
            current = await session.scalar(
                select(func.coalesce(func.max(InteractionEvent.sequence), 0)).where(
                    InteractionEvent.interaction_id == interaction_id
                )
            )
            event = InteractionEvent(
                id=new_id("event"),
                tenant_id=tenant_id,
                interaction_id=interaction_id,
                type=event_type,
                request_id=request_id,
                sequence=int(current or 0) + 1,
                data=data,
            )
            session.add(event)
            await persist_interaction_event_message(
                session,
                interaction,
                event_type,
                terminal_status,
                data,
                event.sequence,
            )
            if terminal_status:
                interaction.status = terminal_status
                # A lease-bound worker may still persist post-terminal diagnostics and
                # checkpoint state. Its finally block releases the lease after that work.
                if (terminal_status in _TERMINAL_STATUSES and lease_owner is None) or (
                    event_type == "ai.interaction.steer.requested" and terminal_status == "accepted"
                ):
                    interaction.runtime_recovery_lease_owner = None
                    interaction.runtime_recovery_lease_until = None
            if runtime_event_sequence is not None:
                interaction.runtime_event_sequence = runtime_event_sequence
            await session.flush()
            view = InteractionEventView(
                type=event.type,
                event_id=event.id,
                request_id=event.request_id,
                occurred_at=event.created_at or utc_now(),
                sequence=event.sequence,
                data=event.data,
            )
        if self.notifier is not None:
            try:
                await self.notifier.publish_interaction_event(interaction_id)
            except Exception:
                logger.exception(
                    "Failed to publish committed interaction event notification",
                    extra={"tenant_id": tenant_id, "interaction_id": interaction_id},
                )
        return view

    async def record_trace(
        self,
        *,
        tenant_id: str,
        interaction_id: str,
        trace_type: str,
        data: dict[str, object],
        lease_owner: str | None = None,
    ) -> InteractionDiagnosticTrace | None:
        async with self.database.session() as session:
            await self.database.set_tenant(session, tenant_id)
            interaction = await session.scalar(
                select(Interaction)
                .where(
                    Interaction.tenant_id == tenant_id,
                    Interaction.id == interaction_id,
                )
                .with_for_update()
            )
            if interaction is None:
                raise ValueError("interaction does not exist")
            if lease_owner is not None and interaction.runtime_recovery_lease_owner != lease_owner:
                return None
            sequence = await session.scalar(
                select(func.coalesce(func.max(InteractionDiagnosticTrace.sequence), 0)).where(
                    InteractionDiagnosticTrace.tenant_id == tenant_id,
                    InteractionDiagnosticTrace.interaction_id == interaction_id,
                )
            )
            trace = InteractionDiagnosticTrace(
                id=new_id("runtime_trace"),
                tenant_id=tenant_id,
                interaction_id=interaction_id,
                type=trace_type,
                sequence=int(sequence or 0) + 1,
                data=data,
                expires_at=interaction.transcript_expires_at,
            )
            session.add(trace)
            await session.flush()
            return trace


async def persist_interaction_event_message(
    session: AsyncSession,
    interaction: Interaction,
    event_type: str,
    terminal_status: str | None,
    data: dict[str, object],
    sequence: int,
) -> None:
    payload = _conversation_message_payload(event_type, terminal_status, data)
    if (
        payload is None
        or interaction.runtime_depth != 0
        or interaction.entry_type == "schedule"
        or not interaction.conversation_id
    ):
        return
    role, direction, content = payload
    message = ConversationMessage(
        id=new_id("conversation_message"),
        tenant_id=interaction.tenant_id,
        interaction_id=interaction.id,
        sequence=sequence,
        agent_id=interaction.agent_id,
        im_channel_id=interaction.im_channel_id,
        im_agent_binding_id=interaction.im_agent_binding_id,
        actor_type=interaction.actor_type,
        actor_id=interaction.actor_id,
        conversation_id=interaction.conversation_id,
        role=role,
        direction=direction,
        content=content,
        expires_at=interaction.transcript_expires_at,
    )
    session.add(message)


def _conversation_message_payload(
    event_type: str,
    terminal_status: str | None,
    data: dict[str, object],
) -> tuple[str, str, str] | None:
    if event_type == "ai.output.completed" and terminal_status in {
        "completed",
        "waiting_user_input",
    }:
        content = data.get("content")
        if isinstance(content, str) and content.strip():
            return "assistant", "outbound", content
    if event_type == "ai.interaction.steer.requested":
        message = data.get("message")
        if isinstance(message, str) and message.strip():
            return "user", "inbound", message
    return None


class InteractionEventNotifier(Protocol):
    async def publish_interaction_event(self, interaction_id: str) -> None: ...
