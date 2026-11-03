from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest

from app.core.config import load_app_config
from app.core.errors import AppError
from app.infrastructure.db.session import DatabaseManager
from app.infrastructure.redis import RedisManager
from app.modules.dashboard.repository import DashboardRepository
from app.modules.dashboard.service import DashboardService
from app.modules.iam.schemas import PrincipalContext


def _principal(tenant_id: str = "tenant_test") -> PrincipalContext:
    return PrincipalContext(
        tenant_id=tenant_id,
        subject_id="user_test",
        username="admin",
        display_name="Admin",
        permissions=("agents.read",),
        tenants=(),
        must_change_password=False,
        request_id="req_test",
    )


@pytest.mark.asyncio
async def test_dashboard_reports_tenant_metrics_and_dependency_state() -> None:
    repository = SimpleNamespace(
        session=object(),
        count_agents=AsyncMock(return_value=4),
        count_capability_configs=AsyncMock(return_value=(2, 6, 3)),
        count_im_entries=AsyncMock(return_value=2),
        count_runs=AsyncMock(return_value=(11, 3)),
    )
    database = SimpleNamespace(set_tenant=AsyncMock(), ping=AsyncMock(return_value=True))
    redis = SimpleNamespace(ping=AsyncMock(return_value=False))
    service = DashboardService(
        cast(DashboardRepository, repository),
        cast(DatabaseManager, database),
        cast(RedisManager, redis),
        load_app_config(),
    )

    result = await service.overview(_principal(), "tenant_test")

    assert result.agents.value == 4
    assert result.im_entries.value == 2
    assert result.runs.value == 11
    assert result.active_runs == 3
    assert result.llm_configs.value == 2
    assert result.skills.value == 6
    assert result.mcp_servers.value == 3
    assert result.service.health == "degraded"
    assert result.dependency_warnings == ("Redis",)
    database.set_tenant.assert_awaited_once_with(repository.session, "tenant_test")


@pytest.mark.asyncio
async def test_dashboard_hides_other_tenant() -> None:
    repository = SimpleNamespace(session=object())
    service = DashboardService(
        cast(DashboardRepository, repository),
        cast(DatabaseManager, SimpleNamespace()),
        cast(RedisManager, SimpleNamespace()),
        load_app_config(),
    )

    with pytest.raises(AppError) as error:
        await service.overview(_principal(), "tenant_other")

    assert error.value.status_code == 404
