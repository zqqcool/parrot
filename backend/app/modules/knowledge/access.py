from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.errors import AppError
from app.infrastructure.db.session import DatabaseManager
from app.modules.iam.permissions import PLATFORM_TENANTS_MANAGE
from app.modules.iam.schemas import PrincipalContext
from app.modules.knowledge.models import KnowledgeSpace
from app.modules.knowledge.repository import KnowledgeRepository


class KnowledgeAccessPolicy:
    """Shared management-plane tenant, permission, and space visibility policy."""

    def __init__(self, session: AsyncSession, database: DatabaseManager) -> None:
        self._session = session
        self._database = database

    async def enter(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        permission: str,
        *,
        not_found_message: str = "Knowledge resource not found",
    ) -> None:
        if (
            principal.tenant_id != tenant_id
            and PLATFORM_TENANTS_MANAGE not in principal.permissions
        ):
            raise AppError("RESOURCE_NOT_FOUND", not_found_message, status.HTTP_404_NOT_FOUND)
        if permission not in principal.permissions:
            raise AppError("FORBIDDEN", "Permission denied", status.HTTP_403_FORBIDDEN)
        await self._database.set_tenant(self._session, tenant_id)

    async def require_space(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        space_id: str,
        permission: str,
        repository: KnowledgeRepository,
        *,
        not_found_message: str = "Knowledge space not found",
    ) -> KnowledgeSpace:
        await self.enter(
            principal,
            tenant_id,
            permission,
            not_found_message=not_found_message,
        )
        return await self.active_space(
            principal,
            tenant_id,
            space_id,
            repository,
            not_found_message=not_found_message,
        )

    @staticmethod
    async def active_space(
        principal: PrincipalContext,
        tenant_id: str,
        space_id: str,
        repository: KnowledgeRepository,
        *,
        not_found_message: str = "Knowledge space not found",
    ) -> KnowledgeSpace:
        space = await repository.get_space(tenant_id, space_id)
        if (
            space is None
            or space.status != "active"
            or not await repository.user_has_access(tenant_id, space_id, principal.subject_id)
        ):
            raise AppError("RESOURCE_NOT_FOUND", not_found_message, status.HTTP_404_NOT_FOUND)
        return space
