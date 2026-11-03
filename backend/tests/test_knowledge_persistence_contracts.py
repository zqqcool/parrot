from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import ClauseElement
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.iam.schemas import UserReference
from app.modules.iam.user_references import UserReferenceResolver
from app.modules.knowledge.document_list_views import document_list_views
from app.modules.knowledge.ingestion_repository import KnowledgeIngestionRepository
from app.modules.knowledge.repository import KnowledgeRepository
from app.modules.knowledge.source_activity_repository import (
    KnowledgeSourceActivityRepository,
)


@pytest.mark.asyncio
async def test_knowledge_space_list_orders_by_newest_creation_time() -> None:
    scalars = AsyncMock(return_value=())
    session = SimpleNamespace(scalars=scalars)
    repository = KnowledgeRepository(cast(AsyncSession, session))

    await repository.list_spaces("tenant_test")

    assert scalars.await_args is not None
    statement = cast(ClauseElement, scalars.await_args.args[0])
    compiled = str(statement.compile(dialect=postgresql.dialect()))
    assert "ORDER BY knowledge_spaces.created_at DESC, knowledge_spaces.id DESC" in compiled


@pytest.mark.asyncio
async def test_document_list_keeps_archived_processing_and_failed_documents_visible() -> None:
    result = SimpleNamespace(tuples=lambda: ())
    execute = AsyncMock(return_value=result)
    session = SimpleNamespace(execute=execute)
    repository = KnowledgeRepository(cast(AsyncSession, session))

    await repository.list_documents("tenant_test", "space_test")

    parameters = _compiled_parameters(execute)
    assert {
        "tenant_test",
        "space_test",
        "active",
        "archived",
        "published",
        "processing",
        "failed",
    } <= parameters


@pytest.mark.asyncio
async def test_document_list_exposes_the_shared_changed_by_user_reference() -> None:
    now = datetime.now(UTC)
    document = SimpleNamespace(
        id="document_test",
        tenant_id="tenant_test",
        space_id="space_test",
        title="Release runbook",
        source_uri=None,
        status="active",
        created_at=now,
        updated_at=now,
    )
    user_references = cast(
        UserReferenceResolver,
        SimpleNamespace(
            resolve=AsyncMock(
                return_value={
                    "user_test": UserReference(
                        id="user_test", display_name="Operator", avatar_present=True
                    )
                }
            )
        ),
    )

    documents = await document_list_views(
        "tenant_test", [(document, 1, 3, "user_test", "Operator")], user_references
    )

    assert documents[0].changed_by_user == UserReference(
        id="user_test", display_name="Operator", avatar_present=True
    )


@pytest.mark.asyncio
async def test_active_ingestion_query_is_tenant_and_space_scoped() -> None:
    result = SimpleNamespace(tuples=lambda: ())
    execute = AsyncMock(return_value=result)
    session = SimpleNamespace(execute=execute)
    repository = KnowledgeIngestionRepository(cast(AsyncSession, session))

    await repository.list_active_jobs("tenant_test", "space_test")

    parameters = _compiled_parameters(execute)
    assert {"tenant_test", "space_test", "queued", "running"} <= parameters


@pytest.mark.asyncio
async def test_source_activity_keeps_pre_document_staging_rows_visible() -> None:
    result = SimpleNamespace(tuples=lambda: ())
    execute = AsyncMock(return_value=result)
    scalar = AsyncMock(return_value=0)
    session = SimpleNamespace(execute=execute, scalar=scalar)
    repository = KnowledgeSourceActivityRepository(cast(AsyncSession, session))

    await repository.list_for_space("tenant_test", "space_test", page=1, page_size=10)

    parameters = _compiled_parameters(execute)
    assert {"tenant_test", "space_test"} <= parameters
    assert "staging" not in parameters
    assert execute.await_args is not None
    statement = cast(ClauseElement, execute.await_args.args[0])
    compiled = str(statement.compile(dialect=postgresql.dialect()))
    assert "LEFT OUTER JOIN knowledge_ingestion_jobs" in compiled
    assert "LEFT OUTER JOIN knowledge_document_versions" in compiled


def _compiled_parameters(execute: AsyncMock) -> set[object]:
    assert execute.await_args is not None
    call_args = cast(tuple[ClauseElement, ...], execute.await_args.args)
    statement = call_args[0]
    compiled = statement.compile(dialect=postgresql.dialect())
    parameters: set[object] = set()
    for value in cast(dict[str, object], compiled.params).values():
        if isinstance(value, list):
            parameters.update(cast(list[object], value))
        else:
            parameters.add(value)
    return parameters
