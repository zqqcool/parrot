from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.infrastructure.db.session import DatabaseManager
from app.modules.iam.schemas import PrincipalContext
from app.modules.knowledge.models import KnowledgeSpace
from app.modules.knowledge.space_deletion_repository import KnowledgeSpaceDeleteBlockers
from app.modules.knowledge.space_deletion_service import KnowledgeSpaceDeletionService


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
        embedding_config_id=None,
        candidate_top_k=20,
        min_vector_score=None,
        rerank_enabled=False,
        reranker_config_id=None,
        rerank_top_n=10,
        min_rerank_score=None,
        retrieval_index_revision=1,
        retrieval_index_status="not_configured",
        access_revision=4,
        created_by_user_id="user_test",
        created_at=now,
        updated_at=now,
    )


def deletion_service(
    repository: object, *, has_access: bool = True
) -> tuple[KnowledgeSpaceDeletionService, SimpleNamespace]:
    session = SimpleNamespace(add=Mock(), flush=AsyncMock())
    instance = KnowledgeSpaceDeletionService(
        cast(AsyncSession, session),
        cast(DatabaseManager, SimpleNamespace(set_tenant=AsyncMock())),
    )
    instance.repository = repository  # type: ignore[assignment]
    instance.spaces = SimpleNamespace(  # type: ignore[assignment]
        user_has_access=AsyncMock(return_value=has_access)
    )
    return instance, session


@pytest.mark.asyncio
async def test_delete_succeeds_with_same_tenant_management_permission() -> None:
    repository = SimpleNamespace(
        get_space_for_update=AsyncMock(return_value=space()),
        blockers=AsyncMock(return_value=KnowledgeSpaceDeleteBlockers(0, 0, 0)),
        delete_space=AsyncMock(),
    )
    instance, session = deletion_service(repository)

    await instance.delete_space(principal("knowledge.spaces.manage"), "tenant_test", "space_test")

    repository.delete_space.assert_awaited_once_with("tenant_test", "space_test")
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_requires_management_permission() -> None:
    repository = SimpleNamespace(get_space_for_update=AsyncMock())
    instance, _session = deletion_service(repository)

    with pytest.raises(AppError) as error:
        await instance.delete_space(principal(), "tenant_test", "space_test")

    assert error.value.status_code == 403
    repository.get_space_for_update.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_hides_cross_tenant_resource() -> None:
    repository = SimpleNamespace(get_space_for_update=AsyncMock())
    instance, _session = deletion_service(repository)

    with pytest.raises(AppError) as error:
        await instance.delete_space(
            principal("knowledge.spaces.manage"), "tenant_other", "space_test"
        )

    assert error.value.status_code == 404
    repository.get_space_for_update.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_hides_space_without_acl_visibility() -> None:
    repository = SimpleNamespace(
        get_space_for_update=AsyncMock(return_value=space()),
        blockers=AsyncMock(),
    )
    instance, _session = deletion_service(repository, has_access=False)

    with pytest.raises(AppError) as error:
        await instance.delete_space(
            principal("knowledge.spaces.manage"), "tenant_test", "space_test"
        )

    assert error.value.status_code == 404
    repository.blockers.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_rejects_content_and_agent_bindings() -> None:
    repository = SimpleNamespace(
        get_space_for_update=AsyncMock(return_value=space()),
        blockers=AsyncMock(return_value=KnowledgeSpaceDeleteBlockers(2, 1, 3)),
        delete_space=AsyncMock(),
    )
    instance, _session = deletion_service(repository)

    with pytest.raises(AppError) as error:
        await instance.delete_space(
            principal("knowledge.spaces.manage"), "tenant_test", "space_test"
        )

    assert error.value.code == "KNOWLEDGE_SPACE_NOT_EMPTY"
    assert error.value.status_code == 409
    assert error.value.details == [
        {"field": "documents", "reason": "2"},
        {"field": "sources", "reason": "1"},
        {"field": "agent_bindings", "reason": "3"},
    ]
    repository.delete_space.assert_not_awaited()
