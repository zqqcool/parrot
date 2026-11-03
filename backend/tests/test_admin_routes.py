from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, Request
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.types import Scope

from app.api.routes import admin_access, admin_tenants, admin_users, health
from app.core.config import load_app_config
from app.core.errors import AppError
from app.modules.iam.models import Session
from app.modules.iam.schemas import (
    PasswordResetRequest,
    PermissionView,
    PrincipalContext,
    RoleCreateRequest,
    RoleView,
    UserCreateRequest,
    UserUpdateRequest,
    UserView,
)
from app.modules.iam.service import AuthenticatedSession
from app.modules.tenancy.schemas import (
    AssignmentRequest,
    GroupCreateRequest,
    GroupView,
    TenantCreateRequest,
    TenantView,
)


class FakeTenancyService:
    def __init__(self) -> None:
        self.tenant = TenantView(id="tenant_test", slug="test", name="Test", status="active")
        self.user = UserView(
            id="user_test",
            username="alex",
            email=None,
            display_name="Alex",
            status="active",
            must_change_password=True,
            avatar_present=False,
        )
        self.group = GroupView(
            id="group_test",
            name="Operators",
            description="",
            status="active",
            is_system=False,
        )
        self.role = RoleView(
            id="role_test",
            key="viewer",
            name="Viewer",
            description="",
            status="active",
            is_system=False,
        )

    async def list_tenants(
        self, _principal: PrincipalContext, *, query: str | None = None
    ) -> list[TenantView]:
        return [self.tenant]

    async def create_tenant(
        self, _principal: PrincipalContext, _payload: TenantCreateRequest
    ) -> TenantView:
        return self.tenant

    async def list_users(
        self, _principal: PrincipalContext, _tenant_id: str, *, query: str | None = None
    ) -> list[UserView]:
        return [self.user]

    async def create_user(
        self, _principal: PrincipalContext, _tenant_id: str, _payload: UserCreateRequest
    ) -> UserView:
        return self.user

    async def update_user(
        self,
        _principal: PrincipalContext,
        _tenant_id: str,
        _user_id: str,
        _payload: UserUpdateRequest,
    ) -> UserView:
        return self.user

    async def reset_password(self, *_args: object) -> None:
        return None

    async def list_groups(
        self, _principal: PrincipalContext, _tenant_id: str, *, query: str | None = None
    ) -> list[GroupView]:
        return [self.group]

    async def create_group(
        self, _principal: PrincipalContext, _tenant_id: str, _payload: GroupCreateRequest
    ) -> GroupView:
        return self.group

    async def replace_group_members(self, *_args: object) -> None:
        return None

    async def get_group_members(self, *_args: object) -> tuple[str, ...]:
        return ("user_test",)

    async def replace_group_roles(self, *_args: object) -> None:
        return None

    async def get_group_roles(self, *_args: object) -> tuple[str, ...]:
        return ("role_test",)

    async def replace_user_roles(self, *_args: object) -> None:
        return None

    async def get_user_roles(self, *_args: object) -> tuple[str, ...]:
        return ("role_test",)

    async def list_roles(
        self, _principal: PrincipalContext, _tenant_id: str, *, query: str | None = None
    ) -> list[RoleView]:
        return [self.role]

    async def create_role(
        self, _principal: PrincipalContext, _tenant_id: str, _payload: RoleCreateRequest
    ) -> RoleView:
        return self.role

    async def list_permissions(self, _principal: PrincipalContext) -> list[PermissionView]:
        return [PermissionView(key="tenant.users.read", description="Read users")]


def request() -> Request:
    app = FastAPI()
    app.state.settings = load_app_config()
    app.state.database = SimpleNamespace()
    scope: Scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [],
        "app": app,
        "client": ("127.0.0.1", 1),
        "server": ("test", 80),
        "scheme": "http",
    }
    value = Request(scope)
    value.state.request_id = "req_test"
    return value


def authenticated() -> AuthenticatedSession:
    principal = PrincipalContext(
        tenant_id="tenant_test",
        subject_id="user_admin",
        username="admin",
        display_name="Admin",
        permissions=("platform.tenants.manage",),
        tenants=(),
        must_change_password=False,
        request_id="req_test",
    )
    return AuthenticatedSession(
        raw_token="session_test",
        session=cast(Session, object()),
        principal=principal,
    )


def service_factory(_request: Request, _session: AsyncSession) -> FakeTenancyService:
    return FakeTenancyService()


@pytest.mark.asyncio
async def test_tenant_and_user_routes_translate_service_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for module in (admin_tenants, admin_users):
        monkeypatch.setattr(module, "_service", service_factory)
    req, auth, db = request(), authenticated(), cast(AsyncSession, object())

    assert (await admin_tenants.list_tenants(req, None, auth, db)).data[0].id == "tenant_test"
    assert (
        await admin_tenants.create_tenant(
            TenantCreateRequest(slug="test-tenant", name="Test"), req, auth, db
        )
    ).data.slug == "test"
    listed_user = await admin_users.list_users("tenant_test", req, None, auth, db)
    assert listed_user.data[0].username == "alex"
    created = await admin_users.create_user(
        "tenant_test",
        UserCreateRequest(
            username="alex",
            display_name="Alex",
            temporary_password="temporary-password",
        ),
        req,
        auth,
        db,
    )
    assert created.data.id == "user_test"
    assert (
        await admin_users.update_user(
            "tenant_test", "user_test", UserUpdateRequest(status="disabled"), req, auth, db
        )
    ).data.status == "active"
    reset = await admin_users.reset_password(
        "tenant_test",
        "user_test",
        PasswordResetRequest(temporary_password="temporary-password"),
        req,
        auth,
        db,
    )
    assert reset.data == {"reset": True}


@pytest.mark.asyncio
async def test_access_routes_translate_assignments(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(admin_access, "_service", service_factory)
    monkeypatch.setattr(admin_access, "_assignment_service", service_factory)
    req, auth, db = request(), authenticated(), cast(AsyncSession, object())

    assert (await admin_access.list_groups("tenant_test", req, None, auth, db)).data[
        0
    ].name == "Operators"
    assert (
        await admin_access.create_group(
            "tenant_test", GroupCreateRequest(name="Operators"), req, auth, db
        )
    ).data.id == "group_test"
    assignment = AssignmentRequest(ids=("item_test",))
    assert (
        await admin_access.replace_group_members(
            "tenant_test", "group_test", assignment, req, auth, db
        )
    ).data["updated"]
    assert (
        await admin_access.get_group_members("tenant_test", "group_test", req, auth, db)
    ).data.ids == ("user_test",)
    assert (
        await admin_access.replace_group_roles(
            "tenant_test", "group_test", assignment, req, auth, db
        )
    ).data["updated"]
    assert (
        await admin_access.get_group_roles("tenant_test", "group_test", req, auth, db)
    ).data.ids == ("role_test",)
    assert (
        await admin_access.replace_user_roles("tenant_test", "user_test", assignment, req, auth, db)
    ).data["updated"]
    assert (
        await admin_access.get_user_roles("tenant_test", "user_test", req, auth, db)
    ).data.ids == ("role_test",)
    listed_role = await admin_access.list_roles("tenant_test", req, None, auth, db)
    assert listed_role.data[0].key == "viewer"
    assert (
        await admin_access.create_role(
            "tenant_test",
            RoleCreateRequest(key="custom.viewer", name="Custom"),
            req,
            auth,
            db,
        )
    ).data.id == "role_test"
    assert (await admin_access.list_permissions(req, auth, db)).data[0].key == "tenant.users.read"


@pytest.mark.asyncio
async def test_health_routes_distinguish_live_and_ready() -> None:
    req = request()
    req.app.state.database = SimpleNamespace(ping=AsyncMock(return_value=True))
    req.app.state.redis = SimpleNamespace(ping=AsyncMock(return_value=True))

    assert (await health.liveness(req)).data.status == "ok"
    assert (await health.readiness(req)).data.dependencies == {"database": "ok", "redis": "ok"}
    req.app.state.redis.ping = AsyncMock(return_value=False)
    with pytest.raises(AppError) as error:
        await health.readiness(req)
    assert error.value.status_code == 503
