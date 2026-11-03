from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules import bootstrap
from app.modules.agents.models import AgentPublication
from app.modules.iam.models import User
from app.modules.tenancy.models import Tenant, TenantMembership


def _result(value: object) -> SimpleNamespace:
    return SimpleNamespace(scalar_one_or_none=lambda: value)


@pytest.mark.asyncio
async def test_bootstrap_does_not_create_business_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = User(
        id="user_admin",
        username="admin",
        normalized_username="admin",
        display_name="平台管理员",
    )
    tenant = Tenant(id="tenant_local", slug="local", name="本地租户")
    membership = TenantMembership(
        id="membership_admin",
        tenant_id=tenant.id,
        user_id=user.id,
    )
    session_mock = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                _result(user),
                _result(tenant),
                _result(membership),
            ]
        ),
        get=AsyncMock(return_value=SimpleNamespace()),
        add=Mock(),
        flush=AsyncMock(),
    )
    monkeypatch.setattr(bootstrap, "sync_permission_catalog", AsyncMock())
    monkeypatch.setattr(
        bootstrap,
        "ensure_platform_role",
        AsyncMock(return_value=SimpleNamespace(id="role_platform_admin")),
    )
    monkeypatch.setattr(
        bootstrap,
        "ensure_tenant_roles",
        AsyncMock(return_value={"tenant_admin": SimpleNamespace(id="role_tenant_admin")}),
    )

    await bootstrap.bootstrap_platform(
        cast(AsyncSession, session_mock),
        username="admin",
        password="temporary-password",
    )

    added_agents = [
        call.args[0]
        for call in session_mock.add.call_args_list
        if isinstance(call.args[0], AgentPublication)
    ]
    assert added_agents == []
