from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import new_id
from app.core.security import hash_password
from app.modules.iam.models import Permission, Role, RolePermission, User, UserRole
from app.modules.iam.permissions import PERMISSION_CATALOG, SYSTEM_ROLES
from app.modules.iam.repository import IamRepository
from app.modules.tenancy.models import MembershipRole, Tenant, TenantMembership


async def sync_permission_catalog(session: AsyncSession) -> None:
    for key, description in PERMISSION_CATALOG.items():
        permission = await session.get(Permission, key)
        if permission is None:
            session.add(Permission(key=key, description=description))
        else:
            permission.description = description
    await session.flush()
    await ensure_platform_role(session)
    tenant_ids = (await session.execute(select(Tenant.id))).scalars().all()
    for tenant_id in tenant_ids:
        await ensure_tenant_roles(session, tenant_id)


async def ensure_platform_role(session: AsyncSession) -> Role:
    role = await _find_role(session, None, "platform_admin")
    if role is None:
        role = Role(
            id=new_id("role"),
            tenant_id=None,
            key="platform_admin",
            name="Platform Administrator",
            description="Full platform and tenant administration",
            is_system=True,
        )
        session.add(role)
        await session.flush()
    await _replace_permissions(session, role, SYSTEM_ROLES["platform_admin"])
    return role


async def ensure_tenant_roles(session: AsyncSession, tenant_id: str) -> dict[str, Role]:
    roles: dict[str, Role] = {}
    for key in ("tenant_admin", "agent_manager", "viewer"):
        role = await _find_role(session, tenant_id, key)
        if role is None:
            role = Role(
                id=new_id("role"),
                tenant_id=tenant_id,
                key=key,
                name=key.replace("_", " ").title(),
                is_system=True,
            )
            session.add(role)
            await session.flush()
        await _replace_permissions(session, role, SYSTEM_ROLES[key])
        roles[key] = role
    return roles


async def bootstrap_platform(
    session: AsyncSession,
    username: str,
    password: str,
    tenant_slug: str = "local",
    tenant_name: str = "本地租户",
) -> User:
    await sync_permission_catalog(session)
    normalized = username.strip().casefold()
    result = await session.execute(select(User).where(User.normalized_username == normalized))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(
            id=new_id("user"),
            username=username.strip(),
            normalized_username=normalized,
            display_name="平台管理员",
            must_change_password=True,
        )
        await IamRepository(session).create_user_with_credential(user, hash_password(password))

    platform_role = await ensure_platform_role(session)
    if await session.get(UserRole, (user.id, platform_role.id)) is None:
        session.add(UserRole(user_id=user.id, role_id=platform_role.id))

    tenant_result = await session.execute(select(Tenant).where(Tenant.slug == tenant_slug))
    tenant = tenant_result.scalar_one_or_none()
    if tenant is None:
        tenant = Tenant(id=new_id("tenant"), slug=tenant_slug, name=tenant_name)
        session.add(tenant)
        await session.flush()
    roles = await ensure_tenant_roles(session, tenant.id)

    membership_result = await session.execute(
        select(TenantMembership).where(
            TenantMembership.tenant_id == tenant.id,
            TenantMembership.user_id == user.id,
        )
    )
    membership = membership_result.scalar_one_or_none()
    if membership is None:
        membership = TenantMembership(id=new_id("membership"), tenant_id=tenant.id, user_id=user.id)
        session.add(membership)
        await session.flush()
    if await session.get(MembershipRole, (membership.id, roles["tenant_admin"].id)) is None:
        session.add(
            MembershipRole(
                tenant_id=tenant.id,
                membership_id=membership.id,
                role_id=roles["tenant_admin"].id,
            )
        )

    await session.flush()
    return user


async def _find_role(session: AsyncSession, tenant_id: str | None, key: str) -> Role | None:
    condition = Role.tenant_id.is_(None) if tenant_id is None else Role.tenant_id == tenant_id
    result = await session.execute(select(Role).where(condition, Role.key == key))
    return result.scalar_one_or_none()


async def _replace_permissions(
    session: AsyncSession,
    role: Role,
    permission_keys: tuple[str, ...],
) -> None:
    result = await session.execute(
        select(RolePermission.permission_key).where(RolePermission.role_id == role.id)
    )
    existing = set(result.scalars())
    for key in set(permission_keys) - existing:
        session.add(
            RolePermission(
                tenant_id=role.tenant_id,
                role_id=role.id,
                permission_key=key,
            )
        )
    for key in existing - set(permission_keys):
        model = await session.get(RolePermission, (role.id, key))
        if model is not None:
            await session.delete(model)
    await session.flush()
