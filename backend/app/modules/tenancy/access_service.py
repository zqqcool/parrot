from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.errors import AppError
from app.infrastructure.db.session import DatabaseManager
from app.modules.audit.service import append_audit
from app.modules.iam.permissions import PLATFORM_TENANTS_MANAGE
from app.modules.iam.repository import IamRepository
from app.modules.iam.schemas import PrincipalContext
from app.modules.tenancy.models import TenantMembership
from app.modules.tenancy.repository import TenancyRepository


class AccessAssignmentService:
    def __init__(self, session: AsyncSession, database: DatabaseManager) -> None:
        self.session = session
        self.database = database
        self.tenancy = TenancyRepository(session)
        self.iam = IamRepository(session)

    async def get_group_members(
        self, principal: PrincipalContext, tenant_id: str, group_id: str
    ) -> tuple[str, ...]:
        await self._enter_tenant(principal, tenant_id, "tenant.groups.read")
        await self._require_group(tenant_id, group_id)
        return await self.tenancy.group_member_user_ids(tenant_id, group_id)

    async def replace_group_members(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        group_id: str,
        user_ids: tuple[str, ...],
    ) -> None:
        await self._enter_tenant(principal, tenant_id, "tenant.groups.manage")
        await self._require_group(tenant_id, group_id)
        membership_ids = await self.tenancy.membership_ids_for_users(tenant_id, user_ids)
        if membership_ids is None:
            raise AppError("RESOURCE_NOT_FOUND", "User not found", status.HTTP_404_NOT_FOUND)
        await self.tenancy.replace_group_members(tenant_id, group_id, membership_ids)
        append_audit(
            self.session,
            principal,
            "group.members.replace",
            "group",
            group_id,
            tenant_id=tenant_id,
        )

    async def get_group_roles(
        self, principal: PrincipalContext, tenant_id: str, group_id: str
    ) -> tuple[str, ...]:
        await self._enter_tenant(principal, tenant_id, "tenant.roles.read")
        await self._require_group(tenant_id, group_id)
        return await self.tenancy.group_role_ids(tenant_id, group_id)

    async def replace_group_roles(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        group_id: str,
        role_ids: tuple[str, ...],
    ) -> None:
        await self._enter_tenant(principal, tenant_id, "tenant.roles.manage")
        await self._require_group(tenant_id, group_id)
        await self._require_roles(tenant_id, role_ids)
        await self.tenancy.replace_group_roles(tenant_id, group_id, role_ids)
        append_audit(
            self.session,
            principal,
            "group.roles.replace",
            "group",
            group_id,
            tenant_id=tenant_id,
        )

    async def get_user_roles(
        self, principal: PrincipalContext, tenant_id: str, user_id: str
    ) -> tuple[str, ...]:
        await self._enter_tenant(principal, tenant_id, "tenant.roles.read")
        membership = await self._require_membership(tenant_id, user_id)
        return await self.tenancy.membership_role_ids(tenant_id, membership.id)

    async def replace_user_roles(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        user_id: str,
        role_ids: tuple[str, ...],
    ) -> None:
        await self._enter_tenant(principal, tenant_id, "tenant.roles.manage")
        membership = await self._require_membership(tenant_id, user_id)
        await self._require_roles(tenant_id, role_ids)
        await self.tenancy.replace_membership_roles(tenant_id, membership.id, role_ids)
        await self.iam.revoke_user_sessions(user_id)
        append_audit(
            self.session,
            principal,
            "user.roles.replace",
            "user",
            user_id,
            tenant_id=tenant_id,
        )

    async def _enter_tenant(
        self, principal: PrincipalContext, tenant_id: str, permission: str
    ) -> None:
        if (
            principal.tenant_id != tenant_id
            and PLATFORM_TENANTS_MANAGE not in principal.permissions
        ):
            raise AppError("RESOURCE_NOT_FOUND", "Resource not found", status.HTTP_404_NOT_FOUND)
        if permission not in principal.permissions:
            raise AppError("FORBIDDEN", "Permission denied", status.HTTP_403_FORBIDDEN)
        await self.database.set_tenant(self.session, tenant_id)

    async def _require_group(self, tenant_id: str, group_id: str) -> None:
        if await self.tenancy.get_group(tenant_id, group_id) is None:
            raise AppError("RESOURCE_NOT_FOUND", "Group not found", status.HTTP_404_NOT_FOUND)

    async def _require_membership(self, tenant_id: str, user_id: str) -> TenantMembership:
        membership = await self.tenancy.get_membership(tenant_id, user_id)
        if membership is None:
            raise AppError("RESOURCE_NOT_FOUND", "User not found", status.HTTP_404_NOT_FOUND)
        return membership

    async def _require_roles(self, tenant_id: str, role_ids: tuple[str, ...]) -> None:
        if not await self.tenancy.roles_exist(tenant_id, role_ids):
            raise AppError("RESOURCE_NOT_FOUND", "Role not found", status.HTTP_404_NOT_FOUND)
