from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, cast

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.core.clock import utc_now
from app.core.errors import AppError
from app.core.ids import new_id
from app.core.task_dispatch import TaskDispatcher
from app.infrastructure.db.session import DatabaseManager
from app.modules.audit.models import AuditLog
from app.modules.schedules.models import ScheduledTask
from app.modules.schedules.runtime_contract import validate_user_provenance
from app.modules.schedules.schemas import ScheduleCreateRequest, ScheduleUpdateRequest
from app.modules.schedules.timing import initial_trigger

_CREATE_FIELDS = frozenset(
    {"title", "input_text", "schedule_type", "cron_expr", "run_at", "timezone"}
)
_UPDATE_FIELDS = frozenset(
    {"title", "input_text", "schedule_type", "cron_expr", "run_at", "timezone"}
)


@dataclass(frozen=True)
class ScheduleRuntimeContext:
    tenant_id: str
    agent_id: str
    actor_type: str
    actor_id: str
    interaction_id: str
    request_id: str
    latest_user_text: str


class ScheduleRuntimePort(Protocol):
    async def handle(
        self, context: ScheduleRuntimeContext, arguments: dict[str, object]
    ) -> dict[str, object]: ...


class SqlScheduleRuntime:
    """User-owned scheduling actions exposed to a root Agent run."""

    def __init__(
        self,
        database: DatabaseManager,
        default_timezone: str,
        dispatcher: TaskDispatcher,
    ) -> None:
        self._database = database
        self._default_timezone = default_timezone
        self._dispatcher = dispatcher

    async def handle(
        self, context: ScheduleRuntimeContext, arguments: dict[str, object]
    ) -> dict[str, object]:
        action = _text(arguments.get("action"))
        if action == "list":
            return await self._list(context)
        if action not in {"create", "update", "cancel"}:
            return _rejected("SCHEDULE_ACTION_INVALID", "Unsupported schedule action")
        try:
            validate_user_provenance(arguments, context.latest_user_text)
            if action == "create":
                return await self._create(context, arguments)
            if action == "update":
                return await self._update(context, arguments)
            return await self._cancel(context, arguments)
        except (AppError, ValidationError, ValueError) as error:
            return _rejected("SCHEDULE_INVALID", str(error))

    async def _list(self, context: ScheduleRuntimeContext) -> dict[str, object]:
        async with self._database.session() as session:
            await self._database.set_tenant(session, context.tenant_id)
            rows = await session.scalars(
                select(ScheduledTask)
                .where(*_ownership_filters(context))
                .order_by(ScheduledTask.created_at.desc())
                .limit(50)
            )
            schedules = [_schedule_view(item) for item in rows]
        return {"status": "ok", "schedules": schedules, "total": len(schedules)}

    async def _create(
        self, context: ScheduleRuntimeContext, arguments: dict[str, object]
    ) -> dict[str, object]:
        payload = ScheduleCreateRequest.model_validate(
            {**_selected(arguments, _CREATE_FIELDS), "agent_id": context.agent_id}
        )
        values = payload.model_dump()
        timezone_name = payload.timezone or self._default_timezone
        values["timezone"] = timezone_name
        next_trigger = initial_trigger(
            payload.schedule_type,
            payload.cron_expr,
            payload.run_at,
            timezone_name,
            utc_now(),
        )
        async with self._database.session() as session:
            await self._database.set_tenant(session, context.tenant_id)
            task = ScheduledTask(
                id=new_id("schedule"),
                tenant_id=context.tenant_id,
                creator_user_id=context.actor_id,
                next_trigger_at=next_trigger,
                status="enabled",
                **values,
            )
            session.add(task)
            await session.flush()
            _append_runtime_audit(session, context, "schedule.agent_create", task.id)
            result: dict[str, object] = {"status": "ok", "schedule": _schedule_view(task)}
        await self._sync_task(task)
        return result

    async def _update(
        self, context: ScheduleRuntimeContext, arguments: dict[str, object]
    ) -> dict[str, object]:
        task_id = _required(arguments, "task_id")
        payload = ScheduleUpdateRequest.model_validate(_selected(arguments, _UPDATE_FIELDS))
        values = payload.model_dump(exclude_unset=True)
        if not values:
            raise ValueError("schedule update has no changes")
        async with self._database.session() as session:
            await self._database.set_tenant(session, context.tenant_id)
            task = await _owned_task(session, context, task_id)
            if task is None:
                return _rejected("SCHEDULE_NOT_FOUND", "Schedule not found")
            _apply_update(task, values)
            _append_runtime_audit(session, context, "schedule.agent_update", task.id)
            await session.flush()
            result: dict[str, object] = {"status": "ok", "schedule": _schedule_view(task)}
        await self._sync_task(task)
        return result

    async def _cancel(
        self, context: ScheduleRuntimeContext, arguments: dict[str, object]
    ) -> dict[str, object]:
        task_id = _required(arguments, "task_id")
        async with self._database.session() as session:
            await self._database.set_tenant(session, context.tenant_id)
            task = await _owned_task(session, context, task_id)
            if task is None:
                return _rejected("SCHEDULE_NOT_FOUND", "Schedule not found")
            task.status = "disabled"
            _append_runtime_audit(session, context, "schedule.agent_cancel", task.id)
            await session.flush()
            result: dict[str, object] = {"status": "ok", "schedule": _schedule_view(task)}
        await self._sync_task(task)
        return result

    async def _sync_task(self, task: ScheduledTask) -> None:
        if task.status == "enabled" and task.next_trigger_at is not None:
            await self._dispatcher.schedule_task(task.tenant_id, task.id, task.next_trigger_at)
            return
        await self._dispatcher.remove_schedule(task.id)


def _apply_update(task: ScheduledTask, values: dict[str, object]) -> None:
    timing_fields = {"schedule_type", "cron_expr", "run_at", "timezone"}
    for key in ("title", "input_text"):
        if key in values:
            setattr(task, key, cast(str, values[key]))
    if not timing_fields.intersection(values):
        return
    schedule_type = cast(str, values.get("schedule_type", task.schedule_type))
    cron_expr = cast(str | None, values.get("cron_expr", task.cron_expr))
    run_at = cast(datetime | None, values.get("run_at", task.run_at))
    timezone_name = cast(str, values.get("timezone", task.timezone))
    if "schedule_type" in values and schedule_type == "once" and "cron_expr" not in values:
        cron_expr = None
    if "schedule_type" in values and schedule_type == "recurring" and "run_at" not in values:
        run_at = None
    task.schedule_type = schedule_type
    task.cron_expr = cron_expr
    task.run_at = run_at
    task.timezone = timezone_name
    task.next_trigger_at = initial_trigger(
        schedule_type, cron_expr, run_at, timezone_name, utc_now()
    )
    if task.status == "completed":
        task.status = "enabled"


async def _owned_task(
    session: AsyncSession, context: ScheduleRuntimeContext, task_id: str
) -> ScheduledTask | None:
    return await session.scalar(
        select(ScheduledTask).where(ScheduledTask.id == task_id, *_ownership_filters(context))
    )


def _ownership_filters(context: ScheduleRuntimeContext) -> tuple[ColumnElement[bool], ...]:
    return (
        ScheduledTask.tenant_id == context.tenant_id,
        ScheduledTask.agent_id == context.agent_id,
        ScheduledTask.creator_user_id == context.actor_id,
    )


def _append_runtime_audit(
    session: AsyncSession, context: ScheduleRuntimeContext, action: str, task_id: str
) -> None:
    session.add(
        AuditLog(
            id=new_id("audit"),
            tenant_id=context.tenant_id,
            actor_type=context.actor_type,
            actor_id=context.actor_id,
            action=action,
            resource_type="schedule",
            resource_id=task_id,
            request_id=context.request_id,
            metadata_json={"interaction_id": context.interaction_id, "agent_id": context.agent_id},
        )
    )


def _schedule_view(task: ScheduledTask) -> dict[str, object]:
    return {
        "id": task.id,
        "title": task.title,
        "schedule_type": task.schedule_type,
        "cron_expr": task.cron_expr,
        "run_at": task.run_at.isoformat() if task.run_at else None,
        "timezone": task.timezone,
        "status": task.status,
        "next_trigger_at": task.next_trigger_at.isoformat() if task.next_trigger_at else None,
        "input_text": task.input_text[:1_000],
    }


def _required(arguments: dict[str, object], key: str) -> str:
    value = _text(arguments.get(key))
    if not value:
        raise ValueError(f"{key} is required")
    return value


def _selected(arguments: dict[str, object], fields: frozenset[str]) -> dict[str, object]:
    return {key: value for key, value in arguments.items() if key in fields}


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _rejected(code: str, message: str) -> dict[str, object]:
    return {"status": "rejected", "code": code, "message": message}
