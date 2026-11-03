from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.session import DatabaseManager
from app.modules.agents.ports import AgentCatalogPort
from app.modules.iam.schemas import PrincipalContext
from app.modules.knowledge.models import KnowledgeSpace
from app.modules.knowledge.repository import KnowledgeRepository
from app.modules.knowledge.service import KnowledgeService


def principal(*permissions: str) -> PrincipalContext:
    return PrincipalContext(
        tenant_id="tenant_test",
        subject_id="user_test",
        username="operator",
        display_name="Operator",
        permissions=permissions,
        tenants=(),
        must_change_password=False,
        request_id="req_test",
    )


def space() -> KnowledgeSpace:
    now = datetime.now(UTC)
    return KnowledgeSpace(
        id="space_test",
        tenant_id="tenant_test",
        slug="engineering",
        name="Engineering",
        classification="standard",
        status="active",
        chunk_size_chars=4_000,
        chunk_overlap_chars=200,
        access_revision=4,
        created_by_user_id="user_test",
        created_at=now,
        updated_at=now,
    )


def service(repository: object) -> KnowledgeService:
    session = SimpleNamespace(add=Mock(), flush=AsyncMock())
    instance = KnowledgeService(
        cast(AsyncSession, session),
        cast(DatabaseManager, SimpleNamespace(set_tenant=AsyncMock())),
        cast(AgentCatalogPort, SimpleNamespace(exists=AsyncMock(return_value=True))),
    )
    instance.repository = repository  # type: ignore[assignment]
    return instance


@pytest.mark.asyncio
async def test_agent_binding_add_is_idempotent_and_preserves_existing_spaces() -> None:
    repository = SimpleNamespace(
        get_space=AsyncMock(return_value=space()),
        user_has_access=AsyncMock(return_value=True),
        add_agent_space=AsyncMock(return_value=True),
        agent_space_ids=AsyncMock(return_value=("space_existing", "space_test")),
    )

    result = await service(repository).add_agent_space(
        principal("agents.manage", "knowledge.spaces.read"),
        "tenant_test",
        "agent_test",
        "space_test",
    )

    assert result.space_ids == ("space_existing", "space_test")
    repository.add_agent_space.assert_awaited_once_with("tenant_test", "agent_test", "space_test")


@pytest.mark.asyncio
async def test_agent_binding_repository_add_uses_conflict_safe_insert() -> None:
    session = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: "binding_test"))
    )
    repository = KnowledgeRepository(cast(AsyncSession, session))

    assert await repository.add_agent_space("tenant_test", "agent_test", "space_test")

    statement = session.execute.await_args.args[0]
    compiled = statement.compile(dialect=postgresql.dialect())
    assert "ON CONFLICT ON CONSTRAINT uq_agent_knowledge_space DO NOTHING" in str(compiled)
    assert {"tenant_test", "agent_test", "space_test"} <= set(compiled.params.values())
