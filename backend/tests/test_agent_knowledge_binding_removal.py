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
async def test_agent_binding_removal_preserves_other_spaces() -> None:
    repository = SimpleNamespace(
        get_space=AsyncMock(return_value=space()),
        user_has_access=AsyncMock(return_value=True),
        remove_agent_space=AsyncMock(return_value=True),
        agent_space_ids=AsyncMock(return_value=("space_other",)),
    )

    result = await service(repository).remove_agent_space(
        principal("agents.manage", "knowledge.spaces.read"),
        "tenant_test",
        "agent_test",
        "space_test",
    )

    assert result.space_ids == ("space_other",)
    repository.remove_agent_space.assert_awaited_once_with(
        "tenant_test", "agent_test", "space_test"
    )


@pytest.mark.asyncio
async def test_space_binding_listing_keeps_disabled_agent_ids_visible() -> None:
    repository = SimpleNamespace(
        get_space=AsyncMock(return_value=space()),
        user_has_access=AsyncMock(return_value=True),
        space_agent_ids=AsyncMock(return_value=("agent_active", "agent_disabled")),
    )

    result = await service(repository).get_space_agents(
        principal("agents.read", "knowledge.spaces.read"),
        "tenant_test",
        "space_test",
    )

    assert result.agent_ids == ("agent_active", "agent_disabled")
    repository.space_agent_ids.assert_awaited_once_with("tenant_test", "space_test")


@pytest.mark.asyncio
async def test_agent_binding_repository_removal_is_tenant_scoped() -> None:
    session = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: "binding_test"))
    )
    repository = KnowledgeRepository(cast(AsyncSession, session))

    assert await repository.remove_agent_space("tenant_test", "agent_test", "space_test")

    statement = session.execute.await_args.args[0]
    compiled = statement.compile(dialect=postgresql.dialect())
    assert "DELETE FROM agent_knowledge_space_bindings" in str(compiled)
    assert {"tenant_test", "agent_test", "space_test"} <= set(compiled.params.values())


@pytest.mark.asyncio
async def test_space_binding_repository_listing_is_tenant_scoped() -> None:
    session = SimpleNamespace(scalars=AsyncMock(return_value=("agent_active", "agent_disabled")))
    repository = KnowledgeRepository(cast(AsyncSession, session))

    assert await repository.space_agent_ids("tenant_test", "space_test") == (
        "agent_active",
        "agent_disabled",
    )

    statement = session.scalars.await_args.args[0]
    compiled = statement.compile(dialect=postgresql.dialect())
    assert "agent_knowledge_space_bindings.tenant_id" in str(compiled)
    assert "agent_knowledge_space_bindings.space_id" in str(compiled)
    assert {"tenant_test", "space_test"} <= set(compiled.params.values())
