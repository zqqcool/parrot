from unittest.mock import AsyncMock, MagicMock, call

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.iam.models import Credential, User
from app.modules.iam.repository import IamRepository


@pytest.mark.asyncio
async def test_user_is_flushed_before_credential_insert() -> None:
    session = MagicMock(spec=AsyncSession)
    session.flush = AsyncMock()
    user = User(
        id="user_test",
        username="admin",
        normalized_username="admin",
        display_name="Admin",
    )

    await IamRepository(session).create_user_with_credential(user, "encoded-password")

    assert session.method_calls[0:2] == [call.add(user), call.flush()]
    credential = session.method_calls[2].args[0]
    assert isinstance(credential, Credential)
    assert credential.user_id == user.id
    assert session.method_calls[3] == call.flush()
