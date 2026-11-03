from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.errors import AppError
from app.modules.audit.service import append_audit
from app.modules.iam.repository import IamRepository
from app.modules.iam.schemas import PrincipalContext


class CurrentUserProfileService:
    """Own-profile mutations that never accept a target user identifier."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.iam = IamRepository(session)

    async def update_display_name(self, principal: PrincipalContext, display_name: str) -> None:
        user = await self.iam.get_user(principal.subject_id)
        if user is None:
            raise AppError("UNAUTHORIZED", "User not found", status.HTTP_401_UNAUTHORIZED)
        normalized_name = display_name.strip()
        if not normalized_name:
            raise AppError(
                "PROFILE_NAME_INVALID",
                "Display name is required",
                status.HTTP_422_UNPROCESSABLE_CONTENT,
            )
        user.display_name = normalized_name
        await self.session.flush()
        append_audit(
            self.session,
            principal,
            "user.profile.update",
            "user",
            user.id,
            {"display_name": normalized_name},
            tenant_id=principal.tenant_id,
        )
