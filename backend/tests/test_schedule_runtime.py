from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest
from _agent_runtime_support import profile, request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.task_dispatch import TaskDispatcher
from app.infrastructure.db.session import DatabaseManager
from app.modules.agent_runtime.plan_tools import tools_for_plan
from app.modules.agent_runtime.planner import AgentPlan
from app.modules.schedules.models import ScheduledTask
from app.modules.schedules.runtime import ScheduleRuntimeContext, SqlScheduleRuntime
from app.modules.schedules.runtime_contract import validate_user_provenance


class SessionContext:
    def __init__(self, session: AsyncSession, events: list[str]) -> None:
        self._session = session
        self._events = events

    async def __aenter__(self) -> AsyncSession:
        return self._session

    async def __aexit__(self, *_: object) -> None:
        self._events.append("commit")


class RecordingScheduleDispatcher:
    def __init__(self, events: list[str]) -> None:
        self._events = events
        self.scheduled: list[tuple[str, str, datetime]] = []
        self.removed: list[str] = []

    async def schedule_task(self, tenant_id: str, schedule_id: str, trigger_at: datetime) -> None:
        self._events.append("schedule")
        self.scheduled.append((tenant_id, schedule_id, trigger_at))

    async def remove_schedule(self, schedule_id: str) -> None:
        self._events.append("remove")
        self.removed.append(schedule_id)


def _context(text: str = "Schedule a report every weekday at 09:00") -> ScheduleRuntimeContext:
    return ScheduleRuntimeContext(
        tenant_id="tenant_test",
        agent_id="agent_test",
        actor_type="anonymous",
        actor_id="visitor_test",
        interaction_id="interaction_test",
        request_id="request_test",
        latest_user_text=text,
    )


def _provenance(text: str) -> dict[str, object]:
    return {
        "source_role": "latest_user_request",
        "source_quote": text,
        "source_span": {"start": 0, "end": len(text)},
    }


def _runtime(
    session: AsyncSession, events: list[str]
) -> tuple[SqlScheduleRuntime, RecordingScheduleDispatcher]:
    database = SimpleNamespace(
        session=Mock(return_value=SessionContext(session, events)),
        set_tenant=AsyncMock(),
    )
    dispatcher = RecordingScheduleDispatcher(events)
    return (
        SqlScheduleRuntime(
            cast(DatabaseManager, database), "UTC", cast(TaskDispatcher, dispatcher)
        ),
        dispatcher,
    )


def test_knowledge_profile_does_not_expose_schedule_tool() -> None:
    knowledge_request = replace(request(), profile=replace(profile(), agent_type_key="knowledge"))

    tools = tools_for_plan(
        knowledge_request,
        AgentPlan(action="agent_loop", synthetic=True),
        script_enabled=True,
        subagent_enabled=True,
    )

    assert "schedule" not in {tool.name for tool in tools}


def test_schedule_changes_require_an_exact_latest_user_span() -> None:
    text = "Schedule a report every weekday at 09:00"
    validate_user_provenance(
        {
            "source_role": "latest_user_request",
            "source_quote": "every weekday",
            "source_span": {"start": 18, "end": 31},
        },
        text,
    )
    with pytest.raises(ValueError, match="does not match"):
        validate_user_provenance(
            {
                "source_role": "latest_user_request",
                "source_quote": "every day",
                "source_span": {"start": 18, "end": 27},
            },
            text,
        )


@pytest.mark.asyncio
async def test_schedule_runtime_rejects_writes_without_user_provenance() -> None:
    runtime = SqlScheduleRuntime(
        cast(DatabaseManager, SimpleNamespace()),
        "UTC",
        cast(TaskDispatcher, SimpleNamespace()),
    )

    result = await runtime.handle(
        _context(),
        {
            "action": "create",
            "title": "Daily report",
            "input_text": "Summarize the report",
            "schedule_type": "recurring",
            "cron_expr": "0 9 * * 1-5",
        },
    )

    assert result["status"] == "rejected"
    assert result["code"] == "SCHEDULE_INVALID"


@pytest.mark.asyncio
async def test_schedule_runtime_registers_create_after_commit() -> None:
    events: list[str] = []
    session = cast(AsyncSession, SimpleNamespace(add=Mock(), flush=AsyncMock()))
    runtime, dispatcher = _runtime(session, events)
    context = _context()

    result = await runtime.handle(
        context,
        {
            "action": "create",
            "title": "Daily report",
            "input_text": "Summarize the report",
            "schedule_type": "recurring",
            "cron_expr": "0 9 * * 1-5",
            **_provenance(context.latest_user_text),
        },
    )

    task = next(
        call.args[0]
        for call in cast(Mock, session.add).call_args_list
        if isinstance(call.args[0], ScheduledTask)
    )
    assert result["status"] == "ok"
    assert dispatcher.scheduled == [("tenant_test", task.id, task.next_trigger_at)]
    assert events == ["commit", "schedule"]


@pytest.mark.asyncio
async def test_schedule_runtime_reschedules_update_after_commit() -> None:
    events: list[str] = []
    task = ScheduledTask(
        id="schedule_test",
        tenant_id="tenant_test",
        agent_id="agent_test",
        creator_user_id="visitor_test",
        title="Daily report",
        input_text="Summarize the report",
        schedule_type="recurring",
        cron_expr="0 9 * * 1-5",
        timezone="UTC",
        status="enabled",
        next_trigger_at=datetime(2026, 7, 21, 9, 0, tzinfo=UTC),
    )
    session = cast(
        AsyncSession,
        SimpleNamespace(scalar=AsyncMock(return_value=task), add=Mock(), flush=AsyncMock()),
    )
    runtime, dispatcher = _runtime(session, events)
    context = _context()

    result = await runtime.handle(
        context,
        {
            "action": "update",
            "task_id": task.id,
            "cron_expr": "0 10 * * 1-5",
            **_provenance(context.latest_user_text),
        },
    )

    assert result["status"] == "ok"
    assert dispatcher.scheduled == [("tenant_test", task.id, task.next_trigger_at)]
    assert events == ["commit", "schedule"]


@pytest.mark.asyncio
async def test_schedule_runtime_removes_cancelled_task_after_commit() -> None:
    events: list[str] = []
    task = ScheduledTask(
        id="schedule_test",
        tenant_id="tenant_test",
        agent_id="agent_test",
        creator_user_id="visitor_test",
        title="Daily report",
        input_text="Summarize the report",
        schedule_type="recurring",
        cron_expr="0 9 * * 1-5",
        timezone="UTC",
        status="enabled",
    )
    session = cast(
        AsyncSession,
        SimpleNamespace(scalar=AsyncMock(return_value=task), add=Mock(), flush=AsyncMock()),
    )
    runtime, dispatcher = _runtime(session, events)
    context = _context()

    result = await runtime.handle(
        context,
        {
            "action": "cancel",
            "task_id": task.id,
            **_provenance(context.latest_user_text),
        },
    )

    assert result["status"] == "ok"
    assert task.status == "disabled"
    assert dispatcher.removed == [task.id]
    assert events == ["commit", "remove"]
