from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.infrastructure.db.session import DatabaseManager
from app.modules.interactions.runtime import RuntimePort
from app.modules.interactions.service import InteractionService


@pytest.mark.asyncio
async def test_actor_owned_interaction_reads_exclude_child_interactions() -> None:
    result = SimpleNamespace(scalar_one_or_none=Mock(return_value=None))
    session = SimpleNamespace(execute=AsyncMock(return_value=result))
    database = SimpleNamespace(set_tenant=AsyncMock())
    service = InteractionService(
        cast(AsyncSession, session),
        cast(DatabaseManager, database),
        cast(RuntimePort, SimpleNamespace()),
    )

    with pytest.raises(AppError, match="Interaction not found"):
        await service.get_owned(
            "interaction_child", "tenant_test", "anonymous", "visitor_test"
        )

    statement = session.execute.await_args.args[0]
    assert "interactions.runtime_depth =" in str(statement)
