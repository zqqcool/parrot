from __future__ import annotations

from typing import Literal, Protocol, cast

from sqlalchemy import select

from app.infrastructure.db.session import DatabaseManager
from app.modules.interactions.models import Interaction
from app.modules.interactions.runtime import RuntimeActiveSkill, RuntimeSkillContext

_ACTIVE_SKILL_PAYLOAD_KEY = "active_skill"
_SKILL_CONTEXT_PAYLOAD_KEY = "skill_context"
_SKILL_CONTEXT_SCHEMA_VERSION = 1
SkillRole = Literal["primary", "supporting"]


class SkillContextCheckpointPort(Protocol):
    async def pin(
        self,
        *,
        tenant_id: str,
        interaction_id: str,
        role: SkillRole,
        skill_id: str,
        skill_version: int,
    ) -> RuntimeSkillContext | None: ...


class ActiveSkillCheckpointPort(Protocol):
    async def activate(
        self,
        *,
        tenant_id: str,
        interaction_id: str,
        skill_id: str,
        skill_version: int,
    ) -> bool: ...


class SqlSkillContextCheckpointStore:
    """Pins versioned primary and supporting Skills in one Interaction."""

    def __init__(self, database: DatabaseManager) -> None:
        self._database = database

    async def pin(
        self,
        *,
        tenant_id: str,
        interaction_id: str,
        role: SkillRole,
        skill_id: str,
        skill_version: int,
    ) -> RuntimeSkillContext | None:
        if (
            role not in {"primary", "supporting"}
            or not skill_id
            or isinstance(skill_version, bool)
            or skill_version < 1
        ):
            return None
        requested = RuntimeActiveSkill(skill_id=skill_id, skill_version=skill_version)
        async with self._database.session() as session:
            await self._database.set_tenant(session, tenant_id)
            interaction = await session.scalar(
                select(Interaction)
                .where(
                    Interaction.tenant_id == tenant_id,
                    Interaction.id == interaction_id,
                )
                .with_for_update()
            )
            if interaction is None:
                return None
            context = runtime_skill_context_from_payload(interaction.input_payload)
            if context is None:
                return None
            updated = pin_skill(context, role=role, requested=requested)
            if updated is None:
                return None
            payload = dict(interaction.input_payload)
            payload.pop(_ACTIVE_SKILL_PAYLOAD_KEY, None)
            payload[_SKILL_CONTEXT_PAYLOAD_KEY] = skill_context_payload(updated)
            interaction.input_payload = payload
            await session.flush()
            return updated

    async def activate(
        self,
        *,
        tenant_id: str,
        interaction_id: str,
        skill_id: str,
        skill_version: int,
    ) -> bool:
        return (
            await self.pin(
                tenant_id=tenant_id,
                interaction_id=interaction_id,
                role="primary",
                skill_id=skill_id,
                skill_version=skill_version,
            )
            is not None
        )


class SqlActiveSkillCheckpointStore(SqlSkillContextCheckpointStore):
    """Compatibility name for callers migrating to SkillContext checkpoints."""


def runtime_active_skill(value: object) -> RuntimeActiveSkill | None:
    if not isinstance(value, dict):
        return None
    payload = cast(dict[str, object], value)
    skill_id = payload.get("skill_id")
    skill_version = payload.get("skill_version")
    if (
        not isinstance(skill_id, str)
        or not skill_id
        or isinstance(skill_version, bool)
        or not isinstance(skill_version, int)
        or skill_version < 1
    ):
        return None
    return RuntimeActiveSkill(skill_id=skill_id, skill_version=skill_version)


def active_skill_payload(value: RuntimeActiveSkill) -> dict[str, object]:
    return {"skill_id": value.skill_id, "skill_version": value.skill_version}


def runtime_skill_context(value: object) -> RuntimeSkillContext | None:
    if not isinstance(value, dict):
        return None
    payload = cast(dict[str, object], value)
    schema_version = payload.get("schema_version")
    supporting_value = payload.get("supporting")
    if (
        isinstance(schema_version, bool)
        or schema_version != _SKILL_CONTEXT_SCHEMA_VERSION
        or not isinstance(supporting_value, list)
    ):
        return None
    primary_value = payload.get("primary")
    primary = runtime_active_skill(primary_value) if primary_value is not None else None
    if primary_value is not None and primary is None:
        return None
    supporting_items = cast(list[object], supporting_value)
    supporting = tuple(runtime_active_skill(item) for item in supporting_items)
    if any(item is None for item in supporting):
        return None
    pinned = tuple(item for item in supporting if item is not None)
    identities = [item.skill_id for item in pinned]
    if primary is not None:
        identities.append(primary.skill_id)
    if len(identities) != len(set(identities)):
        return None
    return RuntimeSkillContext(primary=primary, supporting=pinned)


def runtime_skill_context_from_payload(
    payload: dict[str, object],
) -> RuntimeSkillContext | None:
    if _SKILL_CONTEXT_PAYLOAD_KEY in payload:
        return runtime_skill_context(payload[_SKILL_CONTEXT_PAYLOAD_KEY])
    if _ACTIVE_SKILL_PAYLOAD_KEY not in payload:
        return RuntimeSkillContext()
    active = runtime_active_skill(payload[_ACTIVE_SKILL_PAYLOAD_KEY])
    return RuntimeSkillContext(primary=active) if active is not None else None


def skill_context_payload(value: RuntimeSkillContext) -> dict[str, object]:
    return {
        "schema_version": _SKILL_CONTEXT_SCHEMA_VERSION,
        "primary": active_skill_payload(value.primary) if value.primary is not None else None,
        "supporting": [active_skill_payload(item) for item in value.supporting],
    }


def pin_skill(
    context: RuntimeSkillContext,
    *,
    role: SkillRole,
    requested: RuntimeActiveSkill,
) -> RuntimeSkillContext | None:
    if role == "primary":
        if context.primary is not None:
            return context if context.primary == requested else None
        if any(item.skill_id == requested.skill_id for item in context.supporting):
            return None
        return RuntimeSkillContext(primary=requested, supporting=context.supporting)
    if context.primary is not None and context.primary.skill_id == requested.skill_id:
        return context if context.primary == requested else None
    existing = next(
        (item for item in context.supporting if item.skill_id == requested.skill_id),
        None,
    )
    if existing is not None:
        return context if existing == requested else None
    return RuntimeSkillContext(
        primary=context.primary,
        supporting=(*context.supporting, requested),
    )


def active_skill_conflict(active: RuntimeActiveSkill) -> dict[str, object]:
    return {
        "status": "rejected",
        "code": "ACTIVE_SKILL_CONFLICT",
        "message": f"Skill {active.skill_id} version {active.skill_version} is already active",
    }


def active_skill_unavailable(active: RuntimeActiveSkill) -> dict[str, object]:
    return {
        "status": "rejected",
        "code": "ACTIVE_SKILL_VERSION_UNAVAILABLE",
        "message": f"Pinned Skill {active.skill_id} version {active.skill_version} is unavailable",
    }
