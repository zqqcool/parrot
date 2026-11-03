from __future__ import annotations

import pytest

from app.modules import bootstrap
from app.modules.iam.permissions import PERMISSION_CATALOG


class _ScalarRows:
    def scalars(self) -> _ScalarRows:
        return self

    def all(self) -> list[str]:
        return ["tenant_a", "tenant_b"]


class _Permission:
    def __init__(self, description: str) -> None:
        self.description = description


class _Session:
    def __init__(self, existing_descriptions: dict[str, str] | None = None) -> None:
        self.added_keys: list[str] = []
        self.permissions = {
            key: _Permission(description)
            for key, description in (existing_descriptions or {}).items()
        }

    async def get(self, _model: object, key: str) -> object | None:
        return self.permissions.get(key)

    def add(self, permission: object) -> None:
        self.added_keys.append(permission.key)  # type: ignore[attr-defined]

    async def flush(self) -> None:
        return None

    async def execute(self, _statement: object) -> _ScalarRows:
        return _ScalarRows()


@pytest.mark.asyncio
async def test_permission_sync_refreshes_all_existing_tenant_system_roles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _Session()
    refreshed_tenants: list[str] = []

    async def ensure_platform(_session: object) -> None:
        return None

    async def ensure_tenant(_session: object, tenant_id: str) -> None:
        refreshed_tenants.append(tenant_id)

    monkeypatch.setattr(bootstrap, "ensure_platform_role", ensure_platform)
    monkeypatch.setattr(bootstrap, "ensure_tenant_roles", ensure_tenant)

    await bootstrap.sync_permission_catalog(session)  # type: ignore[arg-type]

    assert set(session.added_keys) == set(PERMISSION_CATALOG)
    assert refreshed_tenants == ["tenant_a", "tenant_b"]


@pytest.mark.asyncio
async def test_permission_sync_updates_existing_catalog_descriptions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _Session({"agents.read": "Read agents"})

    async def ensure_platform(_session: object) -> None:
        return None

    async def ensure_tenant(_session: object, _tenant_id: str) -> None:
        return None

    monkeypatch.setattr(bootstrap, "ensure_platform_role", ensure_platform)
    monkeypatch.setattr(bootstrap, "ensure_tenant_roles", ensure_tenant)

    await bootstrap.sync_permission_catalog(session)  # type: ignore[arg-type]

    assert session.permissions["agents.read"].description == "查看当前租户智能体配置"
