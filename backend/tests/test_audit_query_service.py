from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import ClauseElement
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.infrastructure.db.session import DatabaseManager
from app.modules.audit.service import AuditQueryService
from app.modules.iam.schemas import PrincipalContext


def principal() -> PrincipalContext:
    return PrincipalContext(
        tenant_id="tenant_test",
        subject_id="user_test",
        username="operator",
        display_name="Operator",
        permissions=("audit.read",),
        tenants=(),
        must_change_password=False,
        request_id="req_test",
    )


@pytest.mark.asyncio
async def test_audit_search_is_applied_in_database_before_the_result_limit() -> None:
    scalars = AsyncMock(return_value=[])
    session = SimpleNamespace(scalars=scalars)
    database = SimpleNamespace(set_tenant=AsyncMock())
    service = AuditQueryService(cast(AsyncSession, session), cast(DatabaseManager, database))

    result = await service.list(principal(), "tenant_test", query="release", limit=100)

    assert result == []
    database.set_tenant.assert_awaited_once_with(session, "tenant_test")
    assert scalars.await_args is not None
    statement = cast(ClauseElement, scalars.await_args.args[0])
    compiled = statement.compile(dialect=postgresql.dialect())
    assert compiled.params is not None
    assert "release" in compiled.params.values()
    assert "LIMIT" in str(compiled)


@pytest.mark.asyncio
async def test_audit_query_service_enforces_read_permission() -> None:
    session = SimpleNamespace(scalars=AsyncMock())
    database = SimpleNamespace(set_tenant=AsyncMock())
    service = AuditQueryService(cast(AsyncSession, session), cast(DatabaseManager, database))

    with pytest.raises(AppError) as error:
        await service.list(principal().model_copy(update={"permissions": ()}), "tenant_test")

    assert error.value.code == "FORBIDDEN"
    database.set_tenant.assert_not_awaited()
