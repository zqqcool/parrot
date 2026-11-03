from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.infrastructure.db.session import DatabaseManager
from app.modules.agents.ports import AgentCatalogPort
from app.modules.iam.schemas import PrincipalContext
from app.modules.knowledge.lifecycle_service import KnowledgeDocumentLifecycleService
from app.modules.knowledge.models import (
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeDocumentVersion,
    KnowledgeSpace,
)
from app.modules.knowledge.repository import KnowledgeRepository
from app.modules.knowledge.runtime import (
    KnowledgeRuntimeContext,
    SqlKnowledgeRuntime,
)
from app.modules.knowledge.runtime_repository import KnowledgeRuntimeRepository
from app.modules.knowledge.schemas import (
    KnowledgeDocumentCreateRequest,
    KnowledgeSpaceChunkingUpdateRequest,
    KnowledgeSpaceGrantsRequest,
    KnowledgeTextProcessingSettings,
)
from app.modules.knowledge.service import KnowledgeService


def principal(*permissions: str, tenant_id: str = "tenant_test") -> PrincipalContext:
    return PrincipalContext(
        tenant_id=tenant_id,
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
        chunk_separator=r"\n\n",
        chunk_size_chars=4_000,
        chunk_overlap_chars=200,
        normalize_whitespace=False,
        remove_urls_and_emails=False,
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


def service(repository: object) -> tuple[KnowledgeService, SimpleNamespace]:
    session = SimpleNamespace(
        add=Mock(),
        add_all=Mock(),
        execute=AsyncMock(
            return_value=SimpleNamespace(scalar_one_or_none=lambda: "knowledge_vector_job_test")
        ),
        flush=AsyncMock(),
    )
    instance = KnowledgeService(
        cast(AsyncSession, session),
        cast(DatabaseManager, SimpleNamespace(set_tenant=AsyncMock())),
        cast(AgentCatalogPort, SimpleNamespace(exists=AsyncMock(return_value=True))),
    )
    instance.repository = repository  # type: ignore[assignment]
    return instance, session


def _document_view_stub(*_args: object) -> SimpleNamespace:
    return SimpleNamespace()


@pytest.mark.asyncio
async def test_knowledge_space_hides_cross_tenant_requests_before_repository_access() -> None:
    repository = SimpleNamespace(list_spaces=AsyncMock())
    instance, _session = service(repository)

    with pytest.raises(AppError) as error:
        await instance.list_spaces(principal("knowledge.spaces.read"), "tenant_other")

    assert error.value.status_code == 404
    repository.list_spaces.assert_not_awaited()


@pytest.mark.asyncio
async def test_knowledge_document_creation_requires_current_space_grant() -> None:
    repository = SimpleNamespace(
        get_space=AsyncMock(return_value=space()),
        user_has_access=AsyncMock(return_value=False),
    )
    instance, session = service(repository)

    with pytest.raises(AppError) as error:
        await instance.create_document(
            principal("knowledge.documents.manage"),
            "tenant_test",
            "space_test",
            KnowledgeDocumentCreateRequest(title="Runbook", content="Deploy safely."),
        )

    assert error.value.status_code == 404
    session.add_all.assert_not_called()


@pytest.mark.asyncio
async def test_chunking_settings_apply_only_when_a_document_version_is_created(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = space()
    item.chunk_size_chars = 600
    item.chunk_overlap_chars = 100
    item.chunk_separator = "***"
    item.normalize_whitespace = True
    item.remove_urls_and_emails = True
    repository = SimpleNamespace(
        get_space=AsyncMock(return_value=item),
        user_has_access=AsyncMock(return_value=True),
        available_document_exists=AsyncMock(return_value=False),
    )
    instance, session = service(repository)
    operations: list[str] = []

    def record_add_all(values: object) -> None:
        operations.append("parents" if isinstance(values, tuple) else "chunks")

    session.add_all.side_effect = record_add_all

    async def record_flush() -> None:
        operations.append("flush")

    session.flush.side_effect = record_flush
    monkeypatch.setattr(
        "app.modules.knowledge.service.document_view",
        _document_view_stub,
    )

    await instance.create_document(
        principal("knowledge.documents.manage"),
        "tenant_test",
        "space_test",
        KnowledgeDocumentCreateRequest(title="Runbook", content="A" * 1_300),
    )

    document, version = session.add_all.call_args_list[0].args[0]
    assert version.chunk_size_chars == 600
    assert version.chunk_overlap_chars == 100
    assert version.chunk_separator == "***"
    assert version.normalize_whitespace is True
    assert version.remove_urls_and_emails is True
    assert document.space_id == "space_test"
    assert session.flush.await_count == 2
    assert operations == ["parents", "flush", "chunks", "flush"]


@pytest.mark.asyncio
async def test_manual_document_creation_applies_the_space_processing_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = space()
    item.normalize_whitespace = True
    item.remove_urls_and_emails = True
    repository = SimpleNamespace(
        get_space=AsyncMock(return_value=item),
        user_has_access=AsyncMock(return_value=True),
        available_document_exists=AsyncMock(return_value=False),
    )
    instance, session = service(repository)
    monkeypatch.setattr(
        "app.modules.knowledge.service.document_view",
        _document_view_stub,
    )

    await instance.create_document(
        principal("knowledge.documents.manage"),
        "tenant_test",
        "space_test",
        KnowledgeDocumentCreateRequest(
            title="Release",
            content="  Release\tguide\n\nhttps://docs.example.test  ops@example.test ",
        ),
    )

    _document, version = session.add_all.call_args_list[0].args[0]
    assert version.content == "Release guide"
    assert version.normalize_whitespace is True
    assert version.remove_urls_and_emails is True


@pytest.mark.asyncio
async def test_chunking_settings_require_space_access_and_are_audited() -> None:
    item = space()
    repository = SimpleNamespace(
        get_space=AsyncMock(return_value=item), user_has_access=AsyncMock(return_value=True)
    )
    instance, session = service(repository)

    result = await instance.update_space_chunking(
        principal("knowledge.spaces.manage"),
        "tenant_test",
        "space_test",
        KnowledgeSpaceChunkingUpdateRequest(
            chunk_size_chars=2400,
            chunk_overlap_chars=240,
            chunk_separator="***",
            text_processing=KnowledgeTextProcessingSettings(
                normalize_whitespace=True,
                remove_urls_and_emails=True,
            ),
        ),
    )

    assert result.chunk_size_chars == 2400
    assert result.chunk_overlap_chars == 240
    assert item.chunk_separator == "***"
    assert item.normalize_whitespace is True
    assert item.remove_urls_and_emails is True
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_grant_replacement_validates_targets_and_bumps_access_revision() -> None:
    item = space()
    repository = SimpleNamespace(
        get_space=AsyncMock(return_value=item),
        user_has_access=AsyncMock(return_value=True),
        active_members_exist=AsyncMock(return_value=True),
        active_groups_exist=AsyncMock(return_value=True),
        replace_grants=AsyncMock(),
    )
    instance, _session = service(repository)

    result = await instance.replace_grants(
        principal("knowledge.access.manage"),
        "tenant_test",
        "space_test",
        KnowledgeSpaceGrantsRequest(
            user_ids=("user_second", "user_second"), group_ids=("group_a",)
        ),
    )

    assert result.user_ids == ("user_second",)
    assert result.group_ids == ("group_a",)
    assert result.access_revision == 5
    repository.replace_grants.assert_awaited_once_with(
        "tenant_test", "space_test", ("user_second",), ("group_a",)
    )


@pytest.mark.asyncio
async def test_agent_binding_replacement_requires_management_access_to_existing_spaces() -> None:
    repository = SimpleNamespace(
        agent_space_ids=AsyncMock(return_value=("space_visible", "space_hidden")),
        get_space=AsyncMock(return_value=space()),
        user_has_access=AsyncMock(side_effect=(True, False)),
        replace_agent_spaces=AsyncMock(),
    )
    instance, _session = service(repository)

    with pytest.raises(AppError) as error:
        await instance.replace_agent_spaces(
            principal("agents.manage", "knowledge.spaces.read"),
            "tenant_test",
            "agent_test",
            ("space_visible",),
        )

    assert error.value.status_code == 404
    repository.replace_agent_spaces.assert_not_awaited()


@pytest.mark.asyncio
async def test_sql_runtime_uses_live_agent_binding_without_subject_permissions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence = (
        SimpleNamespace(
            id="chunk_test",
            citation_anchor="chunk-1",
            content="Verified release policy.",
            slide_no=None,
            group_id=None,
            ordinal=1,
            page_kind=None,
        ),
        SimpleNamespace(title="Release policy"),
        SimpleNamespace(id="version_test"),
    )
    repository = SimpleNamespace(
        active_space_ids=AsyncMock(return_value=("space_test",)),
        lexical_search=AsyncMock(return_value=[evidence]),
        authorized_candidates=AsyncMock(return_value=[evidence]),
    )
    session_object = object()

    @asynccontextmanager
    async def session():
        yield session_object

    def repository_factory(_session: AsyncSession) -> SimpleNamespace:
        return repository

    database = SimpleNamespace(session=session, set_tenant=AsyncMock())
    monkeypatch.setattr(
        "app.modules.knowledge.runtime.KnowledgeRuntimeRepository", repository_factory
    )

    result = await SqlKnowledgeRuntime(cast(DatabaseManager, database)).retrieve(
        KnowledgeRuntimeContext(
            tenant_id="tenant_test", agent_id="agent_test", query="release policy"
        )
    )

    assert result.status == "ok"
    assert result.citation_ids == ("chunk_test",)
    repository.lexical_search.assert_awaited_once_with(
        "tenant_test", "agent_test", "release policy", 24
    )
    repository.authorized_candidates.assert_awaited_once_with(
        "tenant_test", "agent_test", ("chunk_test",)
    )
    assert database.set_tenant.await_count == 2


@pytest.mark.asyncio
async def test_agent_knowledge_query_rechecks_binding_and_live_content_states() -> None:
    result = SimpleNamespace(tuples=lambda: ())
    session = SimpleNamespace(execute=AsyncMock(return_value=result))
    repository = KnowledgeRuntimeRepository(cast(AsyncSession, session))

    await repository.lexical_search("tenant_test", "agent_test", "release policy", 6)

    statement = session.execute.await_args.args[0]
    compiled = statement.compile(dialect=postgresql.dialect())
    sql = str(compiled)
    assert "agent_knowledge_space_bindings" in sql
    assert "agent_publications" in sql
    assert {"tenant_test", "agent_test", "knowledge", "active", "published"} <= set(
        compiled.params.values()
    )


@pytest.mark.asyncio
async def test_archiving_document_immediately_removes_its_active_state() -> None:
    now = datetime.now(UTC)
    document = KnowledgeDocument(
        id="document_test",
        tenant_id="tenant_test",
        space_id="space_test",
        title="Release policy",
        status="active",
        created_by_user_id="user_test",
        created_at=now,
        updated_at=now,
    )
    session = SimpleNamespace(add=Mock(), flush=AsyncMock())
    instance = KnowledgeDocumentLifecycleService(
        cast(AsyncSession, session),
        cast(DatabaseManager, SimpleNamespace(set_tenant=AsyncMock())),
    )
    instance.repository = cast(
        KnowledgeRepository,
        SimpleNamespace(
            document_versions=AsyncMock(return_value=(document, ())),
            get_space=AsyncMock(return_value=space()),
            user_has_access=AsyncMock(return_value=True),
        ),
    )

    await instance.archive(principal("knowledge.documents.manage"), "tenant_test", "document_test")

    assert document.status == "archived"
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_manual_document_source_download_is_version_scoped_and_authorized() -> None:
    now = datetime.now(UTC)
    document = KnowledgeDocument(
        id="document_test",
        tenant_id="tenant_test",
        space_id="space_test",
        title="Release policy",
        status="active",
        created_by_user_id="user_test",
        created_at=now,
        updated_at=now,
    )
    version = KnowledgeDocumentVersion(
        id="version_test",
        tenant_id="tenant_test",
        document_id=document.id,
        source_id=None,
        version=1,
        content_sha256="0" * 64,
        status="published",
        extraction_status="completed",
        chunk_size_chars=4000,
        chunk_overlap_chars=200,
        content="Private release policy.",
        created_at=now,
        updated_at=now,
    )
    instance = KnowledgeDocumentLifecycleService(
        cast(AsyncSession, SimpleNamespace(add=Mock())),
        cast(DatabaseManager, SimpleNamespace(set_tenant=AsyncMock())),
    )
    instance.repository = cast(
        KnowledgeRepository,
        SimpleNamespace(
            document_versions=AsyncMock(return_value=(document, (version,))),
            get_space=AsyncMock(return_value=space()),
            user_has_access=AsyncMock(return_value=True),
        ),
    )

    result = await instance.source_file(
        principal("knowledge.documents.read"), "tenant_test", document.id, version.id
    )

    assert result.filename == "Release policy-v1.txt"
    assert result.content == b"Private release policy."
    assert result.content_type == "text/plain; charset=utf-8"


@pytest.mark.asyncio
async def test_document_chunk_view_reads_postgres_chunks_for_an_authorized_version() -> None:
    now = datetime.now(UTC)
    document = KnowledgeDocument(
        id="document_test",
        tenant_id="tenant_test",
        space_id="space_test",
        title="Release policy",
        status="active",
        created_by_user_id="user_test",
        created_at=now,
        updated_at=now,
    )
    version = KnowledgeDocumentVersion(
        id="version_test",
        tenant_id="tenant_test",
        document_id=document.id,
        source_id=None,
        version=1,
        content_sha256="0" * 64,
        status="published",
        extraction_status="completed",
        chunk_size_chars=4000,
        chunk_overlap_chars=200,
        content="Private release policy.",
        created_at=now,
        updated_at=now,
    )
    chunk = KnowledgeChunk(
        id="chunk_test",
        tenant_id="tenant_test",
        space_id="space_test",
        document_version_id=version.id,
        ordinal=1,
        content="Private release policy.",
        citation_anchor="chunk-1",
        search_vector="",
        created_at=now,
        updated_at=now,
    )
    instance = KnowledgeDocumentLifecycleService(
        cast(AsyncSession, SimpleNamespace(add=Mock())),
        cast(DatabaseManager, SimpleNamespace(set_tenant=AsyncMock())),
    )
    document_chunks = AsyncMock(return_value=((chunk,), 1))
    instance.repository = cast(
        KnowledgeRepository,
        SimpleNamespace(
            document_versions=AsyncMock(return_value=(document, (version,))),
            document_chunks=document_chunks,
            get_space=AsyncMock(return_value=space()),
            user_has_access=AsyncMock(return_value=True),
        ),
    )

    result = await instance.list_chunks(
        principal("knowledge.documents.read"),
        "tenant_test",
        document.id,
        version.id,
        page=1,
        page_size=20,
    )

    assert result.total == 1
    assert result.items[0].content == "Private release policy."
    assert result.items[0].content_chars == 23
    document_chunks.assert_awaited_once_with("tenant_test", version.id, page=1, page_size=20)
