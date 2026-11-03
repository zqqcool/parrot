from __future__ import annotations

import logging
from datetime import datetime
from typing import cast

from sqlalchemy import func, select
from starlette import status

from app.core.clock import SYSTEM_CLOCK, Clock
from app.core.errors import AppError
from app.core.ids import new_id
from app.core.task_dispatch import TaskDispatcher
from app.infrastructure.db.session import DatabaseManager
from app.modules.interactions.event_store import InteractionEventNotifier
from app.modules.interactions.models import Interaction, InteractionEvent

logger = logging.getLogger(__name__)


class PendingToolActionController:
    """Resolves one structured action and requeues its owning root after commit."""

    def __init__(
        self,
        database: DatabaseManager,
        dispatcher: TaskDispatcher,
        notifier: InteractionEventNotifier | None = None,
        clock: Clock = SYSTEM_CLOCK,
    ) -> None:
        self._database = database
        self._dispatcher = dispatcher
        self._notifier = notifier
        self._clock = clock

    async def resolve(
        self,
        *,
        tenant_id: str,
        interaction_id: str,
        actor_type: str,
        actor_id: str,
        action_id: str,
        action_hash: str,
        version: str,
        decision: str,
        request_id: str,
    ) -> None:
        if decision not in {"approve", "reject"}:
            raise AppError("AI_PENDING_ACTION_INVALID", "Action decision is invalid", 400)
        async with self._database.session() as session:
            await self._database.set_tenant(session, tenant_id)
            interaction = await session.scalar(
                select(Interaction)
                .where(
                    Interaction.tenant_id == tenant_id,
                    Interaction.id == interaction_id,
                    Interaction.actor_type == actor_type,
                    Interaction.actor_id == actor_id,
                )
                .with_for_update()
            )
            if interaction is None:
                raise AppError(
                    "AI_INTERACTION_NOT_FOUND",
                    "Interaction not found",
                    status.HTTP_404_NOT_FOUND,
                )
            action = _action(interaction)
            _validate_action(
                interaction,
                action,
                tenant_id=tenant_id,
                actor_type=actor_type,
                actor_id=actor_id,
                action_id=action_id,
                action_hash=action_hash,
                version=version,
            )
            expired = _expired(action.get("expires_at"), self._clock.now())
            resolved_status = (
                "expired" if expired else ("approved" if decision == "approve" else "rejected")
            )
            updated = {
                **action,
                "status": resolved_status,
                "decision": decision,
                "resolved_at": self._clock.now().isoformat(),
                "resolved_by": {"actor_type": actor_type, "actor_id": actor_id},
            }
            interaction.input_payload = {
                **interaction.input_payload,
                "pending_tool_action": updated,
            }
            interaction.status = "accepted"
            interaction.runtime_recovery_lease_owner = None
            interaction.runtime_recovery_lease_until = None
            sequence = await session.scalar(
                select(func.coalesce(func.max(InteractionEvent.sequence), 0)).where(
                    InteractionEvent.tenant_id == tenant_id,
                    InteractionEvent.interaction_id == interaction_id,
                )
            )
            session.add(
                InteractionEvent(
                    id=new_id("event"),
                    tenant_id=tenant_id,
                    interaction_id=interaction_id,
                    type="ai.tool.approval.resolved",
                    request_id=request_id,
                    sequence=int(sequence or 0) + 1,
                    data={
                        "action_id": action_id,
                        "decision": decision,
                        "status": resolved_status,
                    },
                )
            )
            await session.flush()
        await self._dispatcher.dispatch_runtime(tenant_id, interaction_id)
        if self._notifier is not None:
            try:
                await self._notifier.publish_interaction_event(interaction_id)
            except Exception:
                logger.exception(
                    "Pending action resolution notification failed after dispatch",
                    extra={
                        "request_id": request_id,
                        "tenant_id": tenant_id,
                        "interaction_id": interaction_id,
                    },
                )


def _action(interaction: Interaction) -> dict[str, object]:
    value = interaction.input_payload.get("pending_tool_action")
    if not isinstance(value, dict):
        raise AppError(
            "AI_PENDING_ACTION_NOT_FOUND",
            "Pending action not found",
            status.HTTP_409_CONFLICT,
        )
    return cast(dict[str, object], value)


def _validate_action(
    interaction: Interaction,
    action: dict[str, object],
    *,
    tenant_id: str,
    actor_type: str,
    actor_id: str,
    action_id: str,
    action_hash: str,
    version: str,
) -> None:
    valid = (
        interaction.status == "waiting_user_action"
        and action.get("status") == "pending"
        and action.get("tenant_id") == tenant_id
        and action.get("actor_type") == actor_type
        and action.get("actor_id") == actor_id
        and action.get("action_id") == action_id
        and action.get("action_hash") == action_hash
        and action.get("version") == version
    )
    if not valid:
        raise AppError(
            "AI_PENDING_ACTION_CONFLICT",
            "Pending action no longer matches this request",
            status.HTTP_409_CONFLICT,
        )


def _expired(value: object, now: datetime) -> bool:
    if not isinstance(value, str):
        return True
    try:
        expiry = datetime.fromisoformat(value)
    except ValueError:
        return True
    if expiry.tzinfo is None or now.tzinfo is None:
        return True
    try:
        return expiry <= now
    except TypeError:
        return True
