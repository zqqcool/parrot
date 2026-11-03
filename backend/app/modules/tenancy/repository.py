from __future__ import annotations

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.iam.models import Role, User
from app.modules.tenancy.models import (
    Group,
    GroupMember,
    GroupRole,
    MembershipRole,
    Tenant,
    TenantMembership,
)


class TenancyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_tenants(self, *, query: str | None = None) -> list[Tenant]:
        statement = select(Tenant)
        normalized = query.strip() if query else ""
        if normalized:
            statement = statement.where(
                or_(
                    Tenant.name.icontains(normalized, autoescape=True),
                    Tenant.slug.icontains(normalized, autoescape=True),
                )
            )
        result = await self.session.execute(statement.order_by(Tenant.name))
        return list(result.scalars())

    async def get_tenant(self, tenant_id: str) -> Tenant | None:
        return await self.session.get(Tenant, tenant_id)

    async def get_tenant_by_slug(self, slug: str) -> Tenant | None:
        result = await self.session.execute(select(Tenant).where(Tenant.slug == slug))
        return result.scalar_one_or_none()

    async def create_tenant(self, tenant: Tenant) -> None:
        self.session.add(tenant)
        await self.session.flush()

    async def list_users(
        self, tenant_id: str, *, query: str | None = None
    ) -> list[tuple[TenantMembership, User]]:
        statement = (
            select(TenantMembership, User)
            .join(User, User.id == TenantMembership.user_id)
            .where(TenantMembership.tenant_id == tenant_id)
        )
        normalized = query.strip() if query else ""
        if normalized:
            statement = statement.where(
                or_(
                    User.display_name.icontains(normalized, autoescape=True),
                    User.username.icontains(normalized, autoescape=True),
                    User.email.icontains(normalized, autoescape=True),
                )
            )
        result = await self.session.execute(statement.order_by(User.display_name))
        return list(result.tuples())

    async def get_membership(self, tenant_id: str, user_id: str) -> TenantMembership | None:
        result = await self.session.execute(
            select(TenantMembership).where(
                TenantMembership.tenant_id == tenant_id,
                TenantMembership.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def membership_ids_for_users(
        self, tenant_id: str, user_ids: tuple[str, ...]
    ) -> tuple[str, ...] | None:
        unique_ids = set(user_ids)
        if not unique_ids:
            return ()
        result = await self.session.execute(
            select(TenantMembership.user_id, TenantMembership.id).where(
                TenantMembership.tenant_id == tenant_id,
                TenantMembership.user_id.in_(unique_ids),
            )
        )
        memberships = dict(result.tuples().all())
        if set(memberships) != unique_ids:
            return None
        return tuple(memberships[user_id] for user_id in sorted(unique_ids))

    async def create_membership(self, membership: TenantMembership) -> None:
        self.session.add(membership)
        await self.session.flush()

    async def list_groups(
        self, tenant_id: str, *, query: str | None = None
    ) -> list[tuple[Group, int]]:
        statement = (
            select(Group, func.count(GroupMember.membership_id))
            .outerjoin(GroupMember, GroupMember.group_id == Group.id)
            .where(Group.tenant_id == tenant_id)
            .group_by(Group.id)
        )
        normalized = query.strip() if query else ""
        if normalized:
            statement = statement.where(
                or_(
                    Group.name.icontains(normalized, autoescape=True),
                    Group.description.icontains(normalized, autoescape=True),
                )
            )
        result = await self.session.execute(statement.order_by(Group.name))
        return [(group, int(count)) for group, count in result.tuples()]

    async def get_group(self, tenant_id: str, group_id: str) -> Group | None:
        result = await self.session.execute(
            select(Group).where(Group.tenant_id == tenant_id, Group.id == group_id)
        )
        return result.scalar_one_or_none()

    async def create_group(self, group: Group) -> None:
        self.session.add(group)
        await self.session.flush()

    async def replace_group_members(
        self,
        tenant_id: str,
        group_id: str,
        membership_ids: tuple[str, ...],
    ) -> None:
        await self.session.execute(delete(GroupMember).where(GroupMember.group_id == group_id))
        self.session.add_all(
            GroupMember(tenant_id=tenant_id, group_id=group_id, membership_id=membership_id)
            for membership_id in sorted(set(membership_ids))
        )
        await self.session.flush()

    async def group_member_user_ids(self, tenant_id: str, group_id: str) -> tuple[str, ...]:
        result = await self.session.execute(
            select(TenantMembership.user_id)
            .join(GroupMember, GroupMember.membership_id == TenantMembership.id)
            .where(GroupMember.tenant_id == tenant_id, GroupMember.group_id == group_id)
            .order_by(TenantMembership.user_id)
        )
        return tuple(result.scalars())

    async def replace_group_roles(
        self,
        tenant_id: str,
        group_id: str,
        role_ids: tuple[str, ...],
    ) -> None:
        await self.session.execute(delete(GroupRole).where(GroupRole.group_id == group_id))
        self.session.add_all(
            GroupRole(tenant_id=tenant_id, group_id=group_id, role_id=role_id)
            for role_id in sorted(set(role_ids))
        )
        await self.session.flush()

    async def group_role_ids(self, tenant_id: str, group_id: str) -> tuple[str, ...]:
        result = await self.session.execute(
            select(GroupRole.role_id)
            .where(GroupRole.tenant_id == tenant_id, GroupRole.group_id == group_id)
            .order_by(GroupRole.role_id)
        )
        return tuple(result.scalars())

    async def replace_membership_roles(
        self,
        tenant_id: str,
        membership_id: str,
        role_ids: tuple[str, ...],
    ) -> None:
        await self.session.execute(
            delete(MembershipRole).where(MembershipRole.membership_id == membership_id)
        )
        self.session.add_all(
            MembershipRole(tenant_id=tenant_id, membership_id=membership_id, role_id=role_id)
            for role_id in sorted(set(role_ids))
        )
        await self.session.flush()

    async def membership_role_ids(self, tenant_id: str, membership_id: str) -> tuple[str, ...]:
        result = await self.session.execute(
            select(MembershipRole.role_id)
            .where(
                MembershipRole.tenant_id == tenant_id,
                MembershipRole.membership_id == membership_id,
            )
            .order_by(MembershipRole.role_id)
        )
        return tuple(result.scalars())

    async def get_role(self, tenant_id: str, role_id: str) -> Role | None:
        result = await self.session.execute(
            select(Role).where(Role.id == role_id, Role.tenant_id == tenant_id)
        )
        return result.scalar_one_or_none()

    async def roles_exist(self, tenant_id: str, role_ids: tuple[str, ...]) -> bool:
        unique_ids = set(role_ids)
        if not unique_ids:
            return True
        result = await self.session.execute(
            select(Role.id).where(Role.tenant_id == tenant_id, Role.id.in_(unique_ids))
        )
        return set(result.scalars()) == unique_ids
