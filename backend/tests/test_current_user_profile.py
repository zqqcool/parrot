from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.iam.profile_service import CurrentUserProfileService
from app.modules.iam.schemas import PrincipalContext


def _principal() -> PrincipalContext:
    return PrincipalContext(
        tenant_id="tenant_test",
        subject_id="user_test",
        username="user",
        display_name="Old name",
        permissions=(),
        tenants=(),
        must_change_password=False,
        request_id="req_test",
    )


@pytest.mark.asyncio
async def test_current_user_profile_updates_only_the_authenticated_user() -> None:
    session = SimpleNamespace(flush=AsyncMock(), add=Mock())
    service = CurrentUserProfileService(cast(AsyncSession, session))
    user = SimpleNamespace(id="user_test", display_name="Old name")
    get_user = AsyncMock(return_value=user)
    cast(Any, service.iam).get_user = get_user

    await service.update_display_name(_principal(), "  New name  ")

    assert user.display_name == "New name"
    get_user.assert_awaited_once_with("user_test")
    session.flush.assert_awaited_once()
