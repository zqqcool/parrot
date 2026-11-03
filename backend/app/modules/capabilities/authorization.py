from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.errors import AppError
from app.infrastructure.db.session import DatabaseManager
from app.modules.iam.permissions import PLATFORM_TENANTS_MANAGE
from app.modules.iam.schemas import PrincipalContext


async def enter_tenant_capability_scope(
    database: DatabaseManager,
    session: AsyncSession,
    principal: PrincipalContext,
    tenant_id: str,
    tenant_permission: str,
    resource_name: str,
) -> None:
    if principal.tenant_id != tenant_id and PLATFORM_TENANTS_MANAGE not in principal.permissions:
        raise AppError(
            "RESOURCE_NOT_FOUND", f"{resource_name} not found", status.HTTP_404_NOT_FOUND
        )
    if tenant_permission not in principal.permissions:
        raise AppError("FORBIDDEN", "Permission denied", status.HTTP_403_FORBIDDEN)
    await database.set_tenant(session, tenant_id)
