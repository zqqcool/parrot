from __future__ import annotations

from app.core.errors import AppError
from app.core.task_dispatch import TaskDispatcher
from app.infrastructure.db.session import DatabaseManager
from app.modules.agent_runtime.pending_action_control import PendingToolActionController
from app.modules.interactions.event_store import InteractionEventNotifier


async def resolve_pending_action_command(
    *,
    database: DatabaseManager,
    dispatcher: TaskDispatcher,
    notifier: InteractionEventNotifier | None,
    tenant_id: str,
    interaction_id: str,
    actor_type: str,
    actor_id: str,
    command_type: str,
    data: dict[str, object],
    request_id: str,
) -> None:
    """Validate an adapter action reference before resolving the durable action."""
    action_id = _required_reference(data, "action_id")
    action_hash = _required_reference(data, "action_hash")
    version = _required_reference(data, "version")
    if command_type not in {"interaction.approve", "interaction.reject"}:
        raise AppError("IM_COMMAND_INVALID", "Action command is invalid", 400)
    await PendingToolActionController(database, dispatcher, notifier).resolve(
        tenant_id=tenant_id,
        interaction_id=interaction_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action_id=action_id,
        action_hash=action_hash,
        version=version,
        decision="approve" if command_type == "interaction.approve" else "reject",
        request_id=request_id,
    )


def _required_reference(data: dict[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise AppError("IM_COMMAND_INVALID", "Action reference is invalid", 400)
    return value
