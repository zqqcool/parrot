from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.agent_runtime import AgentRuntimeProfileResolver
from app.core.clock import utc_now
from app.core.errors import AppError
from app.core.ids import new_id
from app.core.task_dispatch import TaskDispatcher
from app.infrastructure.db.session import DatabaseManager
from app.modules.agents.ports import AgentCatalogPort, AgentRuntimeTarget
from app.modules.audit.service import append_audit
from app.modules.iam.permissions import PLATFORM_TENANTS_MANAGE
from app.modules.iam.schemas import PrincipalContext, UserReference
from app.modules.iam.user_references import UserReferenceResolver
from app.modules.interactions.event_store import InteractionEventNotifier
from app.modules.interactions.models import Interaction
from app.modules.interactions.runtime import RuntimePort
from app.modules.interactions.service import InteractionService, InteractionSubmission
from app.modules.schedules.models import ScheduledTask, ScheduleExecution
from app.modules.schedules.schemas import (
    ScheduleCreateRequest,
    ScheduleExecutionView,
    ScheduleUpdateRequest,
    ScheduleView,
)
from app.modules.schedules.timing import initial_trigger, next_cron_trigger


class ScheduleService:
    def __init__(
        self,
        session: AsyncSession,
        database: DatabaseManager,
        runtime: RuntimePort,
        agents: AgentCatalogPort,
        default_timezone: str,
        notifier: InteractionEventNotifier | None = None,
        profile_resolver: AgentRuntimeProfileResolver | None = None,
        dispatcher: TaskDispatcher | None = None,
    ) -> None:
        self.session = session
        self.database = database
        self.runtime = runtime
        self.agents = agents
        self.default_timezone = default_timezone
        self.notifier = notifier
        self.profile_resolver = profile_resolver
        self.dispatcher = dispatcher

    async def list(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        task_status: str | None,
        *,
        query: str | None = None,
    ) -> list[ScheduleView]:
        await self._enter(principal, tenant_id, "schedules.read")
        statement = select(ScheduledTask).where(ScheduledTask.tenant_id == tenant_id)
        if task_status:
            statement = statement.where(ScheduledTask.status == task_status)
        normalized = query.strip() if query else ""
        if normalized:
            statement = statement.where(
                or_(
                    ScheduledTask.title.icontains(normalized, autoescape=True),
                    ScheduledTask.schedule_type.icontains(normalized, autoescape=True),
                    ScheduledTask.cron_expr.icontains(normalized, autoescape=True),
                )
            )
        rows = await self.session.scalars(statement.order_by(ScheduledTask.created_at.desc()))
        return await self._views(list(rows))

    async def create(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        payload: ScheduleCreateRequest,
    ) -> ScheduleView:
        await self._enter(principal, tenant_id, "schedules.manage")
        await self._agent(tenant_id, payload.agent_id)
        values = payload.model_dump()
        timezone_name = payload.timezone or self.default_timezone
        values["timezone"] = timezone_name
        next_at = initial_trigger(
            payload.schedule_type,
            payload.cron_expr,
            payload.run_at,
            timezone_name,
            utc_now(),
        )
        model = ScheduledTask(
            id=new_id("schedule"),
            tenant_id=tenant_id,
            creator_user_id=principal.subject_id,
            next_trigger_at=next_at,
            **values,
        )
        self.session.add(model)
        await self.session.flush()
        await self._schedule_next(model)
        append_audit(
            self.session, principal, "schedule.create", "schedule", model.id, tenant_id=tenant_id
        )
        return await self._view(model)

    async def update(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        schedule_id: str,
        payload: ScheduleUpdateRequest,
    ) -> ScheduleView:
        await self._enter(principal, tenant_id, "schedules.manage")
        model = await self._get(tenant_id, schedule_id)
        values = payload.model_dump(exclude_unset=True)
        if {"schedule_type", "cron_expr", "run_at", "timezone"} & values.keys():
            schedule_type = str(values.get("schedule_type", model.schedule_type))
            cron_expr = values.get("cron_expr", model.cron_expr)
            run_at = values.get("run_at", model.run_at)
            timezone_name = str(values.get("timezone", model.timezone))
            values["next_trigger_at"] = initial_trigger(
                schedule_type,
                cron_expr if isinstance(cron_expr, str) else None,
                run_at if isinstance(run_at, datetime) else None,
                timezone_name,
                utc_now(),
            )
        if values:
            await self.session.execute(
                update(ScheduledTask)
                .where(ScheduledTask.id == schedule_id, ScheduledTask.tenant_id == tenant_id)
                .values(**values)
            )
            await self.session.refresh(model)
        append_audit(
            self.session,
            principal,
            "schedule.update",
            "schedule",
            model.id,
            values,
            tenant_id=tenant_id,
        )
        await self._schedule_next(model)
        return await self._view(model)

    async def set_enabled(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        schedule_id: str,
        enabled: bool,
    ) -> ScheduleView:
        await self._enter(principal, tenant_id, "schedules.manage")
        model = await self._get(tenant_id, schedule_id)
        if enabled:
            model.next_trigger_at = initial_trigger(
                model.schedule_type,
                model.cron_expr,
                model.run_at,
                model.timezone,
                utc_now(),
            )
        model.status = "enabled" if enabled else "disabled"
        await self.session.flush()
        if enabled:
            await self._schedule_next(model)
        elif self.dispatcher is not None:
            await self.dispatcher.remove_schedule(model.id)
        append_audit(
            self.session,
            principal,
            "schedule.enable" if enabled else "schedule.disable",
            "schedule",
            model.id,
            tenant_id=tenant_id,
        )
        return await self._view(model)

    async def run_now(
        self, principal: PrincipalContext, tenant_id: str, schedule_id: str
    ) -> ScheduleExecutionView:
        await self._enter(principal, tenant_id, "schedules.manage")
        task = await self._get(tenant_id, schedule_id)
        execution = await self._queue(task, utc_now(), "manual")
        await self._execute(task, execution, principal.request_id)
        append_audit(
            self.session,
            principal,
            "schedule.run_now",
            "schedule",
            task.id,
            {"execution_id": execution.id, "status": execution.status},
            tenant_id=tenant_id,
        )
        return await self._execution_view(execution)

    async def executions(
        self, principal: PrincipalContext, tenant_id: str, schedule_id: str
    ) -> list[ScheduleExecutionView]:
        await self._enter(principal, tenant_id, "schedules.read")
        await self._get(tenant_id, schedule_id)
        rows = await self.session.execute(
            select(ScheduleExecution, Interaction.status)
            .outerjoin(Interaction, Interaction.id == ScheduleExecution.interaction_id)
            .where(
                ScheduleExecution.tenant_id == tenant_id,
                ScheduleExecution.schedule_id == schedule_id,
            )
            .order_by(ScheduleExecution.created_at.desc())
            .limit(100)
        )
        return [self.execution_view(item, run_status) for item, run_status in rows.tuples()]

    async def execute_taskiq(
        self, tenant_id: str, schedule_id: str, expected_trigger_at: datetime
    ) -> bool:
        """Execute exactly one TaskIQ-delivered schedule trigger.

        The expected timestamp fences stale TaskIQ messages after an edit or
        disable operation.  It also preserves IANA/DST semantics by computing
        the following trigger with the existing domain timing function.
        """
        await self.database.set_tenant(self.session, tenant_id)
        task = await self.session.scalar(
            select(ScheduledTask)
            .where(ScheduledTask.tenant_id == tenant_id, ScheduledTask.id == schedule_id)
            .with_for_update(skip_locked=True)
        )
        if (
            task is None
            or task.status != "enabled"
            or task.next_trigger_at is None
            or task.next_trigger_at != expected_trigger_at
        ):
            return False
        execution = await self._queue(task, expected_trigger_at, "scheduled")
        task.last_triggered_at = expected_trigger_at
        if task.schedule_type == "once":
            task.status = "completed"
            task.next_trigger_at = None
        else:
            task.next_trigger_at = next_cron_trigger(
                task.cron_expr or "", task.timezone, expected_trigger_at
            )
        await self.session.flush()
        await self._schedule_next(task)
        try:
            await self._execute(task, execution, new_id("request_schedule"))
        except Exception:
            execution.status = "failed"
            execution.error_code = "SCHEDULE_EXECUTION_FAILED"
            await self.session.flush()
            raise
        return True

    async def _schedule_next(self, task: ScheduledTask) -> None:
        if self.dispatcher is None:
            return
        if task.status != "enabled" or task.next_trigger_at is None:
            await self.dispatcher.remove_schedule(task.id)
            return
        await self.dispatcher.schedule_task(task.tenant_id, task.id, task.next_trigger_at)

    async def _execute(
        self, task: ScheduledTask, execution: ScheduleExecution, request_id: str
    ) -> None:
        agent = await self._agent(task.tenant_id, task.agent_id)
        execution.status = "processing"
        await self.session.flush()
        try:
            accepted = await InteractionService(
                self.session,
                self.database,
                self.runtime,
                self.notifier,
                self.profile_resolver,
            ).submit(
                agent,
                InteractionSubmission(
                    actor_type="schedule",
                    actor_id=task.id,
                    entry_type="schedule",
                    input_type="text",
                    request_id=request_id,
                    idempotency_key=execution.id,
                    text=task.input_text,
                ),
            )
        except AppError as exc:
            if exc.code != "AI_PROVIDER_UNAVAILABLE":
                raise
            execution.status = "failed"
            execution.error_code = exc.code
            await self.session.flush()
            return
        execution.interaction_id = accepted.interaction_id
        execution.status = accepted.status
        await self.session.flush()

    async def _queue(
        self, task: ScheduledTask, scheduled_for: datetime, trigger_type: str
    ) -> ScheduleExecution:
        execution = ScheduleExecution(
            id=new_id("schedule_execution"),
            tenant_id=task.tenant_id,
            schedule_id=task.id,
            scheduled_for=scheduled_for,
            trigger_type=trigger_type,
        )
        self.session.add(execution)
        await self.session.flush()
        return execution

    async def _execution_view(self, execution: ScheduleExecution) -> ScheduleExecutionView:
        run_status = None
        if execution.interaction_id:
            run_status = await self.session.scalar(
                select(Interaction.status).where(Interaction.id == execution.interaction_id)
            )
        return self.execution_view(execution, run_status)

    async def _agent(self, tenant_id: str, agent_id: str) -> AgentRuntimeTarget:
        agent = await self.agents.get_published(tenant_id, agent_id)
        if agent is None:
            raise AppError(
                "RESOURCE_NOT_FOUND", "Published agent not found", status.HTTP_404_NOT_FOUND
            )
        return agent

    async def _get(self, tenant_id: str, schedule_id: str) -> ScheduledTask:
        task = await self.session.scalar(
            select(ScheduledTask).where(
                ScheduledTask.tenant_id == tenant_id, ScheduledTask.id == schedule_id
            )
        )
        if task is None:
            raise AppError("RESOURCE_NOT_FOUND", "Schedule not found", status.HTTP_404_NOT_FOUND)
        return task

    async def _enter(self, principal: PrincipalContext, tenant_id: str, permission: str) -> None:
        if (
            principal.tenant_id != tenant_id
            and PLATFORM_TENANTS_MANAGE not in principal.permissions
        ):
            raise AppError("RESOURCE_NOT_FOUND", "Schedule not found", status.HTTP_404_NOT_FOUND)
        if permission not in principal.permissions:
            raise AppError("FORBIDDEN", "Permission denied", status.HTTP_403_FORBIDDEN)
        await self.database.set_tenant(self.session, tenant_id)

    async def _view(self, item: ScheduledTask) -> ScheduleView:
        return self.view(
            item,
            await UserReferenceResolver(self.session).resolve(
                item.tenant_id, (item.creator_user_id,)
            ),
        )

    async def _views(self, items: list[ScheduledTask]) -> list[ScheduleView]:
        users = await UserReferenceResolver(self.session).resolve(
            items[0].tenant_id if items else None, (item.creator_user_id for item in items)
        )
        return [self.view(item, users) for item in items]

    @staticmethod
    def view(item: ScheduledTask, users: Mapping[str, UserReference] | None = None) -> ScheduleView:
        view = ScheduleView.model_validate(item, from_attributes=True)
        return view.model_copy(update={"creator": (users or {}).get(item.creator_user_id)})

    @staticmethod
    def execution_view(item: ScheduleExecution, run_status: str | None) -> ScheduleExecutionView:
        view = ScheduleExecutionView.model_validate(item, from_attributes=True)
        return view.model_copy(update={"status": run_status or item.status})
