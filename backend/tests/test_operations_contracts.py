from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.core.errors import AppError
from app.modules.iam.permissions import SYSTEM_ROLES
from app.modules.memory.schemas import MemoryCreateRequest, MemoryUpdateRequest
from app.modules.schedules.schemas import ScheduleCreateRequest
from app.modules.schedules.timing import initial_trigger, next_cron_trigger


def test_tenant_roles_include_operations_permissions() -> None:
    manager = set(SYSTEM_ROLES["agent_manager"])
    viewer = set(SYSTEM_ROLES["viewer"])

    assert {"memory.read", "memory.manage", "schedules.read", "schedules.manage"} <= manager
    assert {"im.channels.read", "im.channels.manage"} <= manager
    assert {"memory.read", "schedules.read"} <= viewer
    assert "memory.manage" not in viewer


def test_memory_contract_is_strict_and_versioned() -> None:
    payload = MemoryCreateRequest(
        scope_type="tenant",
        scope_id="tenant_test",
        key="deployment-policy",
        content="Use staged rollout",
        memory_type="project_convention",
    )

    assert payload.retention_policy == "user_managed"
    assert MemoryUpdateRequest(content="Updated", expected_version=2).expected_version == 2
    with pytest.raises(ValidationError):
        MemoryCreateRequest.model_validate({**payload.model_dump(), "unknown": True})


def test_schedule_contract_requires_matching_timing_fields() -> None:
    recurring = ScheduleCreateRequest(
        agent_id="agent_test",
        schedule_type="recurring",
        title="Daily",
        input_text="Summarize",
        cron_expr="0 9 * * 1-5",
    )
    assert recurring.timezone is None
    with pytest.raises(ValidationError, match="cron_expr"):
        ScheduleCreateRequest(
            agent_id="agent_test",
            schedule_type="recurring",
            title="Daily",
            input_text="Summarize",
        )
    with pytest.raises(ValidationError, match="run_at"):
        ScheduleCreateRequest(
            agent_id="agent_test",
            schedule_type="once",
            title="Once",
            input_text="Summarize",
        )


def test_schedule_timing_is_timezone_aware_and_future_only() -> None:
    now = datetime(2026, 7, 13, 0, 0, tzinfo=UTC)

    next_at = next_cron_trigger("0 9 * * 1-5", "Asia/Shanghai", now)
    assert next_at.tzinfo is not None
    assert next_at > now
    assert initial_trigger(
        "once", None, now + timedelta(minutes=5), "Asia/Shanghai", now
    ) == now + timedelta(minutes=5)
    with pytest.raises(AppError, match="future"):
        initial_trigger("once", None, now, "Asia/Shanghai", now)
    with pytest.raises(AppError, match="five fields"):
        next_cron_trigger("0 9 * *", "Asia/Shanghai", now)
