from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import utc_now
from app.modules.iam.models import (
    Credential,
    Permission,
    Role,
    RolePermission,
    Session,
    User,
    UserRole,
)
from app.modules.tenancy.models import (
    GroupMember,
    GroupRole,
    MembershipRole,
    Tenant,
    TenantMembership,
)


class IamRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_user_by_username(self, normalized_username: str) -> User | None:
        result = await self.session.execute(
            select(User).where(User.normalized_username == normalized_username)
        )
        return result.scalar_one_or_none()

    async def get_user(self, user_id: str) -> User | None:
        return await self.session.get(User, user_id)

    async def get_credential(self, user_id: str) -> Credential | None:
        return await self.session.get(Credential, user_id)

    async def create_user_with_credential(self, user: User, password_hash: str) -> None:
        self.session.add(user)
        await self.session.flush()
        self.session.add(Credential(user_id=user.id, password_hash=password_hash))
        await self.session.flush()

    async def list_tenant_access(self, user_id: str) -> list[tuple[TenantMembership, Tenant]]:
        result = await self.session.execute(
            select(TenantMembership, Tenant)
            .join(Tenant, Tenant.id == TenantMembership.tenant_id)
            .where(
                TenantMembership.user_id == user_id,
                TenantMembership.status == "active",
                Tenant.status == "active",
            )
            .order_by(Tenant.name)
        )
        return list(result.tuples())

    async def get_membership(self, user_id: str, tenant_id: str) -> TenantMembership | None:
        result = await self.session.execute(
            select(TenantMembership).where(
                TenantMembership.user_id == user_id,
                TenantMembership.tenant_id == tenant_id,
                TenantMembership.status == "active",
            )
        )
        return result.scalar_one_or_none()

    async def effective_permissions(self, user_id: str, tenant_id: str | None) -> set[str]:
        permissions = await self._platform_permissions(user_id)
        if not tenant_id:
            return permissions
        membership = await self.get_membership(user_id, tenant_id)
        if membership is None:
            return permissions

        direct = await self.session.execute(
            select(RolePermission.permission_key)
            .join(MembershipRole, MembershipRole.role_id == RolePermission.role_id)
            .where(
                MembershipRole.membership_id == membership.id,
                MembershipRole.tenant_id == tenant_id,
            )
        )
        permissions.update(direct.scalars())

        grouped = await self.session.execute(
            select(RolePermission.permission_key)
            .join(GroupRole, GroupRole.role_id == RolePermission.role_id)
            .join(GroupMember, GroupMember.group_id == GroupRole.group_id)
            .where(
                GroupMember.membership_id == membership.id,
                GroupMember.tenant_id == tenant_id,
                GroupRole.tenant_id == tenant_id,
            )
        )
        permissions.update(grouped.scalars())
        return permissions

    async def create_session(self, model: Session) -> None:
        self.session.add(model)
        await self.session.flush()

    async def get_session_by_hash(self, token_hash: str) -> Session | None:
        result = await self.session.execute(select(Session).where(Session.token_hash == token_hash))
        return result.scalar_one_or_none()

    async def revoke_session(self, session_id: str, at: datetime | None = None) -> None:
        await self.session.execute(
            update(Session)
            .where(Session.id == session_id, Session.revoked_at.is_(None))
            .values(revoked_at=at or utc_now())
        )

    async def revoke_user_sessions(self, user_id: str) -> None:
        await self.session.execute(
            update(Session)
            .where(Session.user_id == user_id, Session.revoked_at.is_(None))
            .values(revoked_at=utc_now())
        )

    async def set_session_tenant(self, session_id: str, tenant_id: str) -> None:
        await self.session.execute(
            update(Session).where(Session.id == session_id).values(current_tenant_id=tenant_id)
        )

    async def touch_session(
        self, session_id: str, last_seen: datetime, idle_expires: datetime
    ) -> None:
        await self.session.execute(
            update(Session)
            .where(Session.id == session_id)
            .values(last_seen_at=last_seen, idle_expires_at=idle_expires)
        )

    async def update_password(self, user_id: str, encoded_hash: str) -> None:
        await self.session.execute(
            update(Credential)
            .where(Credential.user_id == user_id)
            .values(password_hash=encoded_hash)
        )
        await self.session.execute(
            update(User).where(User.id == user_id).values(must_change_password=False)
        )

    async def replace_role_permissions(
        self, tenant_id: str | None, role_id: str, keys: tuple[str, ...]
    ) -> None:
        await self.session.execute(delete(RolePermission).where(RolePermission.role_id == role_id))
        self.session.add_all(
            RolePermission(tenant_id=tenant_id, role_id=role_id, permission_key=key)
            for key in sorted(set(keys))
        )
        await self.session.flush()

    async def list_permissions(self) -> list[Permission]:
        result = await self.session.execute(select(Permission).order_by(Permission.key))
        return list(result.scalars())

    async def list_roles(self, tenant_id: str, *, query: str | None = None) -> list[Role]:
        statement = select(Role).where(Role.tenant_id == tenant_id)
        normalized = query.strip() if query else ""
        if normalized:
            statement = (
                statement.outerjoin(RolePermission, RolePermission.role_id == Role.id)
                .where(
                    or_(
                        Role.name.icontains(normalized, autoescape=True),
                        Role.key.icontains(normalized, autoescape=True),
                        Role.description.icontains(normalized, autoescape=True),
                        RolePermission.permission_key.icontains(normalized, autoescape=True),
                    )
                )
                .distinct()
            )
        result = await self.session.execute(statement.order_by(Role.name))
        return list(result.scalars())

    async def role_permission_keys(self, role_id: str) -> tuple[str, ...]:
        result = await self.session.execute(
            select(RolePermission.permission_key)
            .where(RolePermission.role_id == role_id)
            .order_by(RolePermission.permission_key)
        )
        return tuple(result.scalars())

    async def _platform_permissions(self, user_id: str) -> set[str]:
        result = await self.session.execute(
            select(RolePermission.permission_key)
            .join(UserRole, UserRole.role_id == RolePermission.role_id)
            .join(Role, Role.id == UserRole.role_id)
            .where(UserRole.user_id == user_id, Role.tenant_id.is_(None), Role.status == "active")
        )
        return set(result.scalars())
