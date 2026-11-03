from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.config import AppConfig
from app.core.errors import AppError
from app.core.ids import new_id
from app.core.security import hash_password
from app.infrastructure.db.session import DatabaseManager
from app.modules.audit.service import append_audit
from app.modules.iam.models import Credential, Role, User
from app.modules.iam.permissions import PLATFORM_TENANTS_MANAGE
from app.modules.iam.repository import IamRepository
from app.modules.iam.schemas import (
    PermissionView,
    PrincipalContext,
    RoleCreateRequest,
    RoleView,
    UserCreateRequest,
    UserUpdateRequest,
    UserView,
)
from app.modules.iam.user_references import UserReferenceResolver
from app.modules.tenancy.models import Group, Tenant, TenantMembership
from app.modules.tenancy.repository import TenancyRepository
from app.modules.tenancy.schemas import (
    GroupCreateRequest,
    GroupView,
    TenantCreateRequest,
    TenantView,
)


class TenancyService:
    def __init__(
        self,
        session: AsyncSession,
        database: DatabaseManager,
        settings: AppConfig,
    ) -> None:
        self.session = session
        self.database = database
        self.settings = settings
        self.tenancy = TenancyRepository(session)
        self.iam = IamRepository(session)

    async def list_tenants(
        self, principal: PrincipalContext, *, query: str | None = None
    ) -> list[TenantView]:
        self._require(principal, PLATFORM_TENANTS_MANAGE)
        return [self._tenant_view(item) for item in await self.tenancy.list_tenants(query=query)]

    async def create_tenant(
        self,
        principal: PrincipalContext,
        payload: TenantCreateRequest,
    ) -> TenantView:
        self._require(principal, PLATFORM_TENANTS_MANAGE)
        if await self.tenancy.get_tenant_by_slug(payload.slug):
            raise AppError(
                "TENANT_CONFLICT", "Tenant slug already exists", status.HTTP_409_CONFLICT
            )
        tenant = Tenant(id=new_id("tenant"), slug=payload.slug, name=payload.name)
        await self.tenancy.create_tenant(tenant)
        await self.database.set_tenant(self.session, tenant.id)
        await ensure_tenant_system_roles(self.session, tenant.id)
        membership = TenantMembership(
            id=new_id("membership"),
            tenant_id=tenant.id,
            user_id=principal.subject_id,
        )
        await self.tenancy.create_membership(membership)
        tenant_admin = await self._role_by_key(tenant.id, "tenant_admin")
        await self.tenancy.replace_membership_roles(tenant.id, membership.id, (tenant_admin.id,))
        append_audit(
            self.session,
            principal,
            "tenant.create",
            "tenant",
            tenant.id,
            tenant_id=tenant.id,
        )
        return self._tenant_view(tenant)

    async def list_users(
        self, principal: PrincipalContext, tenant_id: str, *, query: str | None = None
    ) -> list[UserView]:
        await self._enter_tenant(principal, tenant_id, "tenant.users.read")
        return [
            self._user_view(user)
            for _membership, user in await self.tenancy.list_users(tenant_id, query=query)
        ]

    async def create_user(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        payload: UserCreateRequest,
    ) -> UserView:
        await self._enter_tenant(principal, tenant_id, "tenant.users.manage")
        if len(payload.temporary_password) < self.settings.security.password_min_length:
            raise AppError("AUTH_PASSWORD_WEAK", "Temporary password does not meet policy")
        normalized = payload.username.strip().casefold()
        if await self.iam.get_user_by_username(normalized):
            raise AppError("USER_CONFLICT", "Username already exists", status.HTTP_409_CONFLICT)
        user = User(
            id=new_id("user"),
            username=payload.username.strip(),
            normalized_username=normalized,
            email=payload.email,
            display_name=payload.display_name,
            must_change_password=True,
        )
        await self.iam.create_user_with_credential(
            user,
            hash_password(payload.temporary_password),
        )
        membership = TenantMembership(id=new_id("membership"), tenant_id=tenant_id, user_id=user.id)
        await self.tenancy.create_membership(membership)
        viewer = await self._role_by_key(tenant_id, "viewer")
        await self.tenancy.replace_membership_roles(tenant_id, membership.id, (viewer.id,))
        append_audit(self.session, principal, "user.create", "user", user.id, tenant_id=tenant_id)
        return self._user_view(user)

    async def update_user(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        user_id: str,
        payload: UserUpdateRequest,
    ) -> UserView:
        await self._enter_tenant(principal, tenant_id, "tenant.users.manage")
        if await self.tenancy.get_membership(tenant_id, user_id) is None:
            raise AppError("RESOURCE_NOT_FOUND", "User not found", status.HTTP_404_NOT_FOUND)
        user = await self.iam.get_user(user_id)
        if user is None:
            raise AppError("RESOURCE_NOT_FOUND", "User not found", status.HTTP_404_NOT_FOUND)
        values = payload.model_dump(exclude_none=True)
        if values:
            for key, value in values.items():
                setattr(user, key, value)
        if payload.status == "disabled":
            await self.iam.revoke_user_sessions(user_id)
        await self.session.flush()
        append_audit(
            self.session,
            principal,
            "user.update",
            "user",
            user_id,
            values,
            tenant_id=tenant_id,
        )
        return self._user_view(user)

    async def reset_password(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        user_id: str,
        temporary_password: str,
    ) -> None:
        await self._enter_tenant(principal, tenant_id, "tenant.users.manage")
        if len(temporary_password) < self.settings.security.password_min_length:
            raise AppError("AUTH_PASSWORD_WEAK", "Temporary password does not meet policy")
        if await self.tenancy.get_membership(tenant_id, user_id) is None:
            raise AppError("RESOURCE_NOT_FOUND", "User not found", status.HTTP_404_NOT_FOUND)
        await self.session.execute(
            update(Credential)
            .where(Credential.user_id == user_id)
            .values(password_hash=hash_password(temporary_password))
        )
        await self.session.execute(
            update(User).where(User.id == user_id).values(must_change_password=True)
        )
        await self.iam.revoke_user_sessions(user_id)
        append_audit(
            self.session,
            principal,
            "user.password_reset",
            "user",
            user_id,
            tenant_id=tenant_id,
        )

    async def list_groups(
        self, principal: PrincipalContext, tenant_id: str, *, query: str | None = None
    ) -> list[GroupView]:
        await self._enter_tenant(principal, tenant_id, "tenant.groups.read")
        return [
            GroupView(
                id=group.id,
                name=group.name,
                description=group.description,
                status=group.status,
                is_system=group.is_system,
                member_count=count,
            )
            for group, count in await self.tenancy.list_groups(tenant_id, query=query)
        ]

    async def create_group(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        payload: GroupCreateRequest,
    ) -> GroupView:
        await self._enter_tenant(principal, tenant_id, "tenant.groups.manage")
        group = Group(
            id=new_id("group"),
            tenant_id=tenant_id,
            name=payload.name,
            description=payload.description,
        )
        await self.tenancy.create_group(group)
        append_audit(
            self.session, principal, "group.create", "group", group.id, tenant_id=tenant_id
        )
        return GroupView(
            id=group.id,
            name=group.name,
            description=group.description,
            status=group.status,
            is_system=group.is_system,
        )

    async def list_roles(
        self, principal: PrincipalContext, tenant_id: str, *, query: str | None = None
    ) -> list[RoleView]:
        await self._enter_tenant(principal, tenant_id, "tenant.roles.read")
        result: list[RoleView] = []
        for role in await self.iam.list_roles(tenant_id, query=query):
            result.append(self._role_view(role, await self.iam.role_permission_keys(role.id)))
        return result

    async def create_role(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        payload: RoleCreateRequest,
    ) -> RoleView:
        await self._enter_tenant(principal, tenant_id, "tenant.roles.manage")
        valid = {permission.key for permission in await self.iam.list_permissions()}
        if not set(payload.permissions).issubset(valid):
            raise AppError("ROLE_PERMISSION_INVALID", "Role contains unknown permissions")
        role = Role(
            id=new_id("role"),
            tenant_id=tenant_id,
            key=payload.key,
            name=payload.name,
            description=payload.description,
        )
        self.session.add(role)
        await self.session.flush()
        await self.iam.replace_role_permissions(tenant_id, role.id, payload.permissions)
        append_audit(self.session, principal, "role.create", "role", role.id, tenant_id=tenant_id)
        return self._role_view(role, payload.permissions)

    async def list_permissions(self, principal: PrincipalContext) -> list[PermissionView]:
        if not principal.permissions:
            raise AppError("FORBIDDEN", "Permission denied", status.HTTP_403_FORBIDDEN)
        return [
            PermissionView(key=item.key, description=item.description)
            for item in await self.iam.list_permissions()
        ]

    async def _enter_tenant(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        permission: str,
    ) -> None:
        if (
            principal.tenant_id != tenant_id
            and PLATFORM_TENANTS_MANAGE not in principal.permissions
        ):
            raise AppError("RESOURCE_NOT_FOUND", "Resource not found", status.HTTP_404_NOT_FOUND)
        self._require(principal, permission)
        await self.database.set_tenant(self.session, tenant_id)

    def _require(self, principal: PrincipalContext, permission: str) -> None:
        if permission not in principal.permissions:
            raise AppError("FORBIDDEN", "Permission denied", status.HTTP_403_FORBIDDEN)

    async def _role_by_key(self, tenant_id: str, key: str) -> Role:
        result = await self.session.execute(
            select(Role).where(Role.tenant_id == tenant_id, Role.key == key)
        )
        role = result.scalar_one_or_none()
        if role is None:
            raise RuntimeError(f"Missing system role: {key}")
        return role

    @staticmethod
    def _tenant_view(item: Tenant) -> TenantView:
        return TenantView(id=item.id, slug=item.slug, name=item.name, status=item.status)

    @staticmethod
    def _user_view(item: User) -> UserView:
        return UserView(
            **UserReferenceResolver.view(item).model_dump(),
            username=item.username,
            email=item.email,
            status=item.status,
            must_change_password=item.must_change_password,
        )

    @staticmethod
    def _role_view(item: Role, keys: tuple[str, ...]) -> RoleView:
        return RoleView(
            id=item.id,
            key=item.key,
            name=item.name,
            description=item.description,
            status=item.status,
            is_system=item.is_system,
            permissions=keys,
        )


async def ensure_tenant_system_roles(session: AsyncSession, tenant_id: str) -> None:
    from app.modules.bootstrap import ensure_tenant_roles

    await ensure_tenant_roles(session, tenant_id)
