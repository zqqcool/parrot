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
from app.modules.knowledge.ingestion_repository import KnowledgeIngestionRepository
from app.modules.knowledge.models import KnowledgeDocument, KnowledgeSpace
from app.modules.knowledge.repository import KnowledgeRepository
from app.modules.knowledge.schemas import KnowledgeDocumentTextVersionCreateRequest
from app.modules.knowledge.text_version_service import KnowledgeDocumentTextVersionService


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
        status="active",
        chunk_separator=r"\n\n",
        chunk_size_chars=4_000,
        chunk_overlap_chars=200,
        normalize_whitespace=False,
        remove_urls_and_emails=False,
        embedding_config_id=None,
        created_by_user_id="user_test",
        created_at=now,
        updated_at=now,
    )


def document() -> KnowledgeDocument:
    now = datetime.now(UTC)
    return KnowledgeDocument(
        id="document_test",
        tenant_id="tenant_test",
        space_id="space_test",
        source_id="source_old",
        title="Release runbook",
        title_key="release runbook",
        status="active",
        created_by_user_id="user_test",
        created_at=now,
        updated_at=now,
    )


def service() -> tuple[KnowledgeDocumentTextVersionService, SimpleNamespace, AsyncMock, AsyncMock]:
    session = SimpleNamespace(add=Mock(), add_all=Mock(), execute=AsyncMock(), flush=AsyncMock())
    instance = KnowledgeDocumentTextVersionService(
        cast(AsyncSession, session), cast(DatabaseManager, SimpleNamespace(set_tenant=AsyncMock()))
    )
    instance.access = cast(
        KnowledgeRepository,
        SimpleNamespace(
            get_space=AsyncMock(return_value=space()), user_has_access=AsyncMock(return_value=True)
        ),
    )
    get_document_for_update = AsyncMock(return_value=document())
    supersede_published_versions = AsyncMock()
    instance.versions = cast(
        KnowledgeIngestionRepository,
        SimpleNamespace(
            get_document_for_update=get_document_for_update,
            replacement_pending=AsyncMock(return_value=False),
            next_version_number=AsyncMock(return_value=2),
            published_version_ids=AsyncMock(return_value=("version_old",)),
            supersede_published_versions=supersede_published_versions,
        ),
    )
    return instance, session, supersede_published_versions, get_document_for_update


@pytest.mark.asyncio
async def test_text_replacement_creates_an_immutable_published_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instance, session, supersede_published_versions, _get_document_for_update = service()
    queued_vector_jobs: list[tuple[str, str]] = []

    def document_view_stub(*_args: object) -> SimpleNamespace:
        return SimpleNamespace()

    monkeypatch.setattr(
        "app.modules.knowledge.text_version_service.document_view", document_view_stub
    )

    async def enqueue(
        _session: object,
        _tenant_id: str,
        version_id: str,
        action: str,
        **_kwargs: object,
    ) -> None:
        queued_vector_jobs.append((version_id, action))

    monkeypatch.setattr("app.modules.knowledge.text_version_service.enqueue_vector_job", enqueue)

    await instance.replace(
        principal("knowledge.documents.manage"),
        "tenant_test",
        "document_test",
        KnowledgeDocumentTextVersionCreateRequest(content="Deploy only after approval."),
    )

    version = next(
        call.args[0]
        for call in session.add.call_args_list
        if getattr(call.args[0], "document_id", None) == "document_test"
    )
    assert version.document_id == "document_test"
    assert version.version == 2
    assert version.status == "published"
    assert version.source_id is None
    assert version.content == "Deploy only after approval."
    assert list(session.add_all.call_args.args[0])[0].document_version_id == version.id
    assert queued_vector_jobs == [("version_old", "delete")]
    supersede_published_versions.assert_awaited_once_with("tenant_test", "document_test")


@pytest.mark.asyncio
async def test_text_replacement_hides_cross_tenant_requests_before_document_lookup() -> None:
    instance, _session, _supersede_published_versions, get_document_for_update = service()

    with pytest.raises(AppError) as error:
        await instance.replace(
            principal("knowledge.documents.manage", tenant_id="tenant_other"),
            "tenant_test",
            "document_test",
            KnowledgeDocumentTextVersionCreateRequest(content="Deploy only after approval."),
        )

    assert error.value.status_code == 404
    get_document_for_update.assert_not_awaited()
