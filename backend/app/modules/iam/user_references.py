from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.iam.models import User
from app.modules.iam.schemas import UserReference
from app.modules.tenancy.models import TenantMembership


class UserReferenceResolver:
    """Build the safe, reusable user projection used by resource responses."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def resolve(
        self, tenant_id: str | None, user_ids: Iterable[str | None]
    ) -> dict[str, UserReference]:
        ids = {user_id for user_id in user_ids if user_id}
        if not ids:
            return {}
        statement = select(User).where(User.id.in_(ids))
        if tenant_id is not None:
            statement = statement.join(TenantMembership).where(
                TenantMembership.tenant_id == tenant_id,
                TenantMembership.status == "active",
            )
        result = await self.session.scalars(statement)
        return {user.id: self.view(user, avatar_present=tenant_id is not None) for user in result}

    async def search_ids(self, tenant_id: str, query: str) -> tuple[str, ...]:
        normalized = query.strip()
        if not normalized:
            return ()
        rows = await self.session.scalars(
            select(User.id)
            .join(TenantMembership, TenantMembership.user_id == User.id)
            .where(
                TenantMembership.tenant_id == tenant_id,
                TenantMembership.status == "active",
                or_(
                    User.display_name.icontains(normalized, autoescape=True),
                    User.username.icontains(normalized, autoescape=True),
                    User.email.icontains(normalized, autoescape=True),
                ),
            )
        )
        return tuple(rows)

    @staticmethod
    def view(user: User, *, avatar_present: bool = True) -> UserReference:
        return UserReference(
            id=user.id,
            display_name=user.display_name,
            avatar_present=avatar_present and bool(user.avatar_key and user.avatar_content_type),
        )
