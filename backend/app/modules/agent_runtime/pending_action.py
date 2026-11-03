from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from typing import Protocol, cast

from sqlalchemy import select

from app.core.clock import SYSTEM_CLOCK, Clock
from app.core.ids import new_id
from app.infrastructure.db.session import DatabaseManager
from app.modules.agent_runtime.contracts import ChatMessage, ToolCall
from app.modules.agent_runtime.resume_snapshot import create_resume_snapshot
from app.modules.interactions.models import Interaction
from app.modules.interactions.runtime import RuntimeRequest

_ACTION_TTL = timedelta(minutes=15)


class PendingToolActionPort(Protocol):
    async def prepare(
        self,
        request: RuntimeRequest,
        call: ToolCall,
        value: dict[str, object],
        messages: list[ChatMessage],
    ) -> dict[str, object]: ...

    async def mark_executing(self, request: RuntimeRequest, action: dict[str, object]) -> bool: ...

    async def mark_completed(
        self,
        request: RuntimeRequest,
        action: dict[str, object],
        result: dict[str, object],
    ) -> None: ...


class SqlPendingToolActionStore:
    """Persists one actor-bound action in the root Interaction payload."""

    def __init__(self, database: DatabaseManager, clock: Clock = SYSTEM_CLOCK) -> None:
        self._database = database
        self._clock = clock

    async def prepare(
        self,
        request: RuntimeRequest,
        call: ToolCall,
        value: dict[str, object],
        messages: list[ChatMessage],
    ) -> dict[str, object]:
        private = _mapping(value.get("pending_action"))
        snapshot = create_resume_snapshot(messages, exclude_tool_call_id=call.id)
        now = self._clock.now()
        identity: dict[str, object] = {
            "capability_id": _required(private, "capability_id"),
            "server_id": _required(private, "server_id"),
            "tool_name": _required(private, "tool_name"),
            "arguments": _mapping(private.get("arguments")),
            "schema_hash": _required(private, "schema_hash"),
            "effect": _required(private, "effect"),
            "approval": _required(private, "approval"),
        }
        action_hash = _action_hash(identity)
        action: dict[str, object] = {
            "version": "v1",
            "action_id": new_id("pending_action"),
            "action_hash": action_hash,
            "status": "pending",
            "tenant_id": request.tenant_id,
            "actor_type": request.actor_type,
            "actor_id": request.actor_id,
            "call_id": call.id,
            **identity,
            "resume_messages": list(snapshot),
            "created_at": now.isoformat(),
            "expires_at": (now + _ACTION_TTL).isoformat(),
        }
        async with self._database.session() as session:
            await self._database.set_tenant(session, request.tenant_id)
            interaction = await session.scalar(
                select(Interaction)
                .where(
                    Interaction.tenant_id == request.tenant_id,
                    Interaction.id == request.interaction_id,
                )
                .with_for_update()
            )
            if interaction is None:
                raise ValueError("Interaction is unavailable")
            existing = _mapping_or_none(interaction.input_payload.get("pending_tool_action"))
            if existing is not None:
                if (
                    existing.get("status") == "pending"
                    and existing.get("action_hash") == action_hash
                ):
                    return _public_wait(existing)
                raise ValueError("Interaction already has a pending tool action")
            interaction.input_payload = {
                **interaction.input_payload,
                "pending_tool_action": action,
            }
            await session.flush()
        return _public_wait(action)

    async def mark_executing(self, request: RuntimeRequest, action: dict[str, object]) -> bool:
        return await self._transition(
            request,
            action,
            expected="approved",
            status="executing",
            extra={"execution_started_at": self._clock.now().isoformat()},
        )

    async def mark_completed(
        self,
        request: RuntimeRequest,
        action: dict[str, object],
        result: dict[str, object],
    ) -> None:
        changed = await self._transition(
            request,
            action,
            expected="executing",
            status="completed",
            extra={"result": result, "execution_completed_at": self._clock.now().isoformat()},
        )
        if not changed:
            raise ValueError("Pending tool action is not executing")

    async def _transition(
        self,
        request: RuntimeRequest,
        action: dict[str, object],
        *,
        expected: str,
        status: str,
        extra: dict[str, object],
    ) -> bool:
        async with self._database.session() as session:
            await self._database.set_tenant(session, request.tenant_id)
            interaction = await session.scalar(
                select(Interaction)
                .where(
                    Interaction.tenant_id == request.tenant_id,
                    Interaction.id == request.interaction_id,
                )
                .with_for_update()
            )
            if interaction is None:
                return False
            current = _mapping_or_none(interaction.input_payload.get("pending_tool_action"))
            if (
                current is None
                or current.get("action_id") != action.get("action_id")
                or current.get("action_hash") != action.get("action_hash")
                or current.get("status") != expected
            ):
                return False
            updated = {**current, "status": status, **extra}
            interaction.input_payload = {
                **interaction.input_payload,
                "pending_tool_action": updated,
            }
            await session.flush()
            action.clear()
            action.update(updated)
            return True


def _public_wait(action: dict[str, object]) -> dict[str, object]:
    return {
        "status": "waiting_approval",
        "code": "MCP_APPROVAL_REQUIRED",
        "action_id": action["action_id"],
        "action_hash": action["action_hash"],
        "version": action["version"],
        "message": "此操作需要你的明确确认。",
    }


def _action_hash(value: dict[str, object]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _required(value: dict[str, object], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item:
        raise ValueError(f"Pending tool action {key} is invalid")
    return item


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("Pending tool action payload is invalid")
    return cast(dict[str, object], value)


def _mapping_or_none(value: object) -> dict[str, object] | None:
    return cast(dict[str, object], value) if isinstance(value, dict) else None
