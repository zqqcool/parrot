from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.object_storage import (
    ObjectData,
    ObjectStorageDestinationConflictError,
    ObjectStorageOperationError,
    ObjectStoragePort,
    ObjectUploadGrant,
)
from app.core.task_dispatch import TaskDispatcher
from app.infrastructure.db.session import DatabaseManager
from app.modules.iam.schemas import PrincipalContext
from app.modules.knowledge.extractor import KnowledgeExtractionError, extract_text
from app.modules.knowledge.ingestion_repository import KnowledgeIngestionRepository
from app.modules.knowledge.ingestion_service import KnowledgeIngestionService
from app.modules.knowledge.ingestion_validation import validate_uploaded_file
from app.modules.knowledge.models import (
    KnowledgeDocument,
    KnowledgeDocumentVersion,
    KnowledgeIngestionJob,
    KnowledgeSource,
    KnowledgeSpace,
)
from app.modules.knowledge.repository import KnowledgeRepository
from app.modules.knowledge.schemas import (
    KnowledgeDocumentVersionUploadRequest,
    KnowledgeIngestionView,
    KnowledgeSourceConfirmRequest,
    KnowledgeSourceUploadRequest,
)


class InMemoryObjectStorage:
    def __init__(self) -> None:
        self.objects: dict[str, ObjectData] = {}
        self.moves: list[tuple[str, str]] = []
        self.reject_existing_move = False
        self.move_error: ObjectStorageOperationError | None = None

    async def issue_upload_grant(
        self, key: str, content_type: str, size_bytes: int
    ) -> ObjectUploadGrant:
        return ObjectUploadGrant(
            object_key=key,
            upload_key=f"parrot/{key}",
            upload_token="upload-token",
            expires_at=datetime.now(UTC) + timedelta(minutes=15),
        )

    async def write(self, key: str, content: bytes, content_type: str) -> None:
        self.objects[key] = ObjectData(content=content, content_type=content_type)

    async def move(self, source_key: str, target_key: str) -> None:
        self.moves.append((source_key, target_key))
        if self.move_error is not None:
            raise self.move_error
        if self.reject_existing_move and target_key in self.objects:
            raise ObjectStorageDestinationConflictError()
        self.objects[target_key] = self.objects.pop(source_key)

    async def read(self, key: str) -> ObjectData | None:
        return self.objects.get(key)

    async def delete(self, key: str) -> None:
        self.objects.pop(key, None)


def _principal() -> PrincipalContext:
    return PrincipalContext(
        tenant_id="tenant_test",
        subject_id="user_test",
        username="operator",
        display_name="Operator",
        permissions=("knowledge.documents.manage",),
        tenants=(),
        must_change_password=False,
        request_id="req_test",
    )


def _space() -> KnowledgeSpace:
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
        access_revision=1,
        created_by_user_id="user_test",
        created_at=now,
        updated_at=now,
    )


def _upload_source(
    *,
    status: str = "staging",
    staging_key: str | None = "staging/knowledge/release.md",
    object_key: str | None = None,
) -> KnowledgeSource:
    return KnowledgeSource(
        id="source_test",
        tenant_id="tenant_test",
        space_id="space_test",
        source_kind="upload",
        title="Release runbook",
        original_filename="release.md",
        content_type="text/markdown",
        declared_size_bytes=15,
        staging_key=staging_key,
        object_key=object_key,
        status=status,
        created_by_user_id="user_test",
    )


def _queued_state(
    source: KnowledgeSource,
) -> tuple[KnowledgeIngestionJob, KnowledgeDocumentVersion, KnowledgeDocument]:
    document = KnowledgeDocument(
        id="document_test",
        tenant_id=source.tenant_id,
        space_id=source.space_id,
        source_id=source.id,
        title=source.title,
        title_key="release runbook",
        status="processing",
        created_by_user_id=source.created_by_user_id,
    )
    version = KnowledgeDocumentVersion(
        id="version_test",
        tenant_id=source.tenant_id,
        document_id=document.id,
        source_id=source.id,
        version=1,
        content_sha256="a" * 64,
        created_by_user_id=source.created_by_user_id,
        content="",
    )
    job = KnowledgeIngestionJob(
        id="job_test",
        tenant_id=source.tenant_id,
        source_id=source.id,
        document_version_id=version.id,
        status="queued",
        attempts=0,
    )
    return job, version, document


def _service(
    storage: InMemoryObjectStorage, dispatcher: SimpleNamespace | None = None
) -> tuple[KnowledgeIngestionService, SimpleNamespace]:
    session = SimpleNamespace(add=Mock(), add_all=Mock(), flush=AsyncMock(), commit=AsyncMock())
    service = KnowledgeIngestionService(
        cast(AsyncSession, session),
        cast(DatabaseManager, SimpleNamespace(set_tenant=AsyncMock())),
        cast(ObjectStoragePort, storage),
        1024,
        dispatcher=cast(TaskDispatcher | None, dispatcher),
    )
    service.access = cast(
        KnowledgeRepository,
        SimpleNamespace(
            get_space=AsyncMock(return_value=_space()),
            user_has_access=AsyncMock(return_value=True),
            available_document_exists=AsyncMock(return_value=False),
        ),
    )
    return service, session


@pytest.mark.asyncio
async def test_confirmed_upload_commits_before_task_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = InMemoryObjectStorage()
    events: list[str] = []
    dispatcher = SimpleNamespace(dispatch_knowledge_ingestion=AsyncMock())
    service, session = _service(storage, dispatcher)
    source = _upload_source()
    storage.objects[cast(str, source.staging_key)] = ObjectData(
        content=b"Release runbook", content_type="text/markdown"
    )
    service.repository = cast(
        KnowledgeIngestionRepository,
        SimpleNamespace(get_source_for_update=AsyncMock(return_value=source)),
    )

    def record_commit() -> None:
        events.append("commit")

    def record_dispatch(_tenant_id: str, _job_id: str) -> None:
        events.append("dispatch")

    def empty_view(
        _job: KnowledgeIngestionJob, _document: KnowledgeDocument
    ) -> KnowledgeIngestionView:
        return cast(KnowledgeIngestionView, SimpleNamespace())

    session.commit.side_effect = record_commit
    dispatcher.dispatch_knowledge_ingestion.side_effect = record_dispatch
    monkeypatch.setattr("app.modules.knowledge.ingestion_service._ingestion_view", empty_view)

    await service.confirm_upload(
        _principal(),
        "tenant_test",
        source.id,
        KnowledgeSourceConfirmRequest(staging_key=cast(str, source.staging_key)),
    )

    assert events == ["commit", "dispatch"]


@pytest.mark.asyncio
async def test_confirm_upload_replays_the_existing_queued_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = InMemoryObjectStorage()
    dispatcher = SimpleNamespace(dispatch_knowledge_ingestion=AsyncMock())
    service, session = _service(storage, dispatcher)
    source = _upload_source(
        status="queued",
        staging_key=None,
        object_key="knowledge/tenant_test/space_test/source_test/source.md",
    )
    job, version, document = _queued_state(source)
    service.repository = cast(
        KnowledgeIngestionRepository,
        SimpleNamespace(
            get_source_for_update=AsyncMock(return_value=source),
            get_job_by_source=AsyncMock(return_value=(job, version, document)),
        ),
    )
    expected = cast(KnowledgeIngestionView, SimpleNamespace(id=job.id))

    def existing_view(
        _job: KnowledgeIngestionJob, _document: KnowledgeDocument
    ) -> KnowledgeIngestionView:
        return expected

    monkeypatch.setattr("app.modules.knowledge.ingestion_service._ingestion_view", existing_view)

    result = await service.confirm_upload(
        _principal(),
        "tenant_test",
        source.id,
        KnowledgeSourceConfirmRequest(staging_key="staging/knowledge/release.md"),
    )

    assert result is expected
    session.commit.assert_awaited_once()
    dispatcher.dispatch_knowledge_ingestion.assert_awaited_once_with("tenant_test", job.id)
    assert storage.moves == []


@pytest.mark.asyncio
async def test_confirm_upload_keeps_the_committed_job_when_dispatch_fails() -> None:
    storage = InMemoryObjectStorage()
    dispatcher = SimpleNamespace(
        dispatch_knowledge_ingestion=AsyncMock(side_effect=RuntimeError("queue unavailable"))
    )
    service, session = _service(storage, dispatcher)
    source = _upload_source()
    staging_key = cast(str, source.staging_key)
    storage.objects[staging_key] = ObjectData(
        content=b"Release runbook", content_type="text/markdown"
    )
    service.repository = cast(
        KnowledgeIngestionRepository,
        SimpleNamespace(get_source_for_update=AsyncMock(return_value=source)),
    )

    with pytest.raises(AppError) as error:
        await service.confirm_upload(
            _principal(),
            "tenant_test",
            source.id,
            KnowledgeSourceConfirmRequest(staging_key=staging_key),
        )

    assert error.value.code == "DEPENDENCY_UNAVAILABLE"
    assert error.value.status_code == 503
    session.commit.assert_awaited_once()
    assert source.status == "queued"
    assert cast(str, source.object_key) in storage.objects
    assert staging_key not in storage.objects


@pytest.mark.asyncio
async def test_knowledge_upload_grant_is_scoped_to_one_space_source() -> None:
    service, session = _service(InMemoryObjectStorage())

    source, grant = await service.issue_upload(
        _principal(),
        "tenant_test",
        "space_test",
        KnowledgeSourceUploadRequest(
            title="Release runbook",
            filename="release.md",
            content_type="text/markdown",
            size_bytes=20,
        ),
    )

    assert grant.object_key == source.staging_key
    assert grant.object_key.startswith("staging/knowledge/tenant_test/space_test/")
    session.add.assert_any_call(source)


def test_knowledge_upload_rejects_content_type_spoofing() -> None:
    with pytest.raises(AppError) as error:
        validate_uploaded_file(b"not a PDF", "application/pdf", "policy.pdf", 1024)

    assert error.value.code == "KNOWLEDGE_FILE_CONTENT_INVALID"


def test_text_extraction_is_bounded_and_rejects_empty_files() -> None:
    assert extract_text(b"Deployment policy", "text/plain", 100, 10) == "Deployment policy"
    with pytest.raises(KnowledgeExtractionError, match="KNOWLEDGE_DOCUMENT_EMPTY"):
        extract_text(b"\n\n", "text/plain", 100, 10)


@pytest.mark.asyncio
async def test_confirmed_upload_snapshots_its_space_chunking_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = InMemoryObjectStorage()
    service, session = _service(storage)
    space = _space()
    space.chunk_size_chars = 2400
    space.chunk_overlap_chars = 240
    space.chunk_separator = "***"
    space.normalize_whitespace = True
    space.remove_urls_and_emails = True
    service.access = cast(
        KnowledgeRepository,
        SimpleNamespace(
            get_space=AsyncMock(return_value=space),
            user_has_access=AsyncMock(return_value=True),
            available_document_exists=AsyncMock(return_value=False),
        ),
    )
    source, grant = await service.issue_upload(
        _principal(),
        "tenant_test",
        "space_test",
        KnowledgeSourceUploadRequest(
            title="Release runbook",
            filename="release.md",
            content_type="text/markdown",
            size_bytes=15,
        ),
    )
    source.status = "staging"
    storage.objects[grant.object_key] = ObjectData(
        content=b"Release runbook", content_type="text/markdown"
    )
    service.repository = cast(
        KnowledgeIngestionRepository,
        SimpleNamespace(get_source_for_update=AsyncMock(return_value=source)),
    )

    def ingestion_view(
        _job: KnowledgeIngestionJob, _document: KnowledgeDocument
    ) -> KnowledgeIngestionView:
        return cast(KnowledgeIngestionView, SimpleNamespace())

    monkeypatch.setattr(
        "app.modules.knowledge.ingestion_service._ingestion_view",
        ingestion_view,
    )

    await service.confirm_upload(
        _principal(),
        "tenant_test",
        source.id,
        KnowledgeSourceConfirmRequest(staging_key=grant.object_key),
    )

    _document, version, _job = session.add_all.call_args.args[0]
    assert version.source_id == source.id
    assert version.chunk_size_chars == 2400
    assert version.chunk_overlap_chars == 240
    assert version.chunk_separator == "***"
    assert version.normalize_whitespace is True
    assert version.remove_urls_and_emails is True
    assert storage.moves == [(grant.object_key, cast(str, source.object_key))]
    assert grant.object_key not in storage.objects


@pytest.mark.asyncio
async def test_replacement_upload_targets_an_existing_authorized_document() -> None:
    storage = InMemoryObjectStorage()
    service, _session = _service(storage)
    document = KnowledgeDocument(
        id="document_test",
        tenant_id="tenant_test",
        space_id="space_test",
        title="Release runbook",
        status="active",
        created_by_user_id="user_test",
    )
    service.repository = cast(
        KnowledgeIngestionRepository,
        SimpleNamespace(get_document=AsyncMock(return_value=document)),
    )

    source, _grant = await service.issue_replacement_upload(
        _principal(),
        "tenant_test",
        document.id,
        KnowledgeDocumentVersionUploadRequest(
            filename="release-2026.md",
            content_type="text/markdown",
            size_bytes=32,
        ),
    )

    assert source.target_document_id == document.id
    assert source.space_id == document.space_id
    assert source.title == document.title


@pytest.mark.asyncio
async def test_upload_grant_rejects_a_duplicate_available_title() -> None:
    service, session = _service(InMemoryObjectStorage())
    service.access = cast(
        KnowledgeRepository,
        SimpleNamespace(
            get_space=AsyncMock(return_value=_space()),
            user_has_access=AsyncMock(return_value=True),
            available_document_exists=AsyncMock(return_value=True),
        ),
    )

    with pytest.raises(AppError) as error:
        await service.issue_upload(
            _principal(),
            "tenant_test",
            "space_test",
            KnowledgeSourceUploadRequest(
                title="Release runbook",
                filename="release.md",
                content_type="text/markdown",
                size_bytes=20,
            ),
        )

    assert error.value.code == "KNOWLEDGE_DOCUMENT_TITLE_CONFLICT"
    assert error.value.status_code == 409
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_confirmed_replacement_creates_next_immutable_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = InMemoryObjectStorage()
    service, session = _service(storage)
    document = KnowledgeDocument(
        id="document_test",
        tenant_id="tenant_test",
        space_id="space_test",
        source_id="source_old",
        title="Release runbook",
        status="active",
        created_by_user_id="user_test",
    )
    source = KnowledgeSource(
        id="source_new",
        tenant_id="tenant_test",
        space_id="space_test",
        source_kind="upload",
        title="Release runbook 2026",
        original_filename="release-2026.md",
        content_type="text/markdown",
        declared_size_bytes=20,
        staging_key="staging/knowledge/release-2026.md",
        target_document_id=document.id,
        status="staging",
        created_by_user_id="user_test",
    )
    staging_key = cast(str, source.staging_key)
    storage.objects[staging_key] = ObjectData(
        content=b"Updated release policy", content_type="text/markdown"
    )
    service.repository = cast(
        KnowledgeIngestionRepository,
        SimpleNamespace(
            get_source_for_update=AsyncMock(return_value=source),
            get_document_for_update=AsyncMock(return_value=document),
            replacement_pending=AsyncMock(return_value=False),
            next_version_number=AsyncMock(return_value=2),
        ),
    )

    def ingestion_view(
        _job: KnowledgeIngestionJob, _document: KnowledgeDocument
    ) -> KnowledgeIngestionView:
        return cast(KnowledgeIngestionView, SimpleNamespace())

    monkeypatch.setattr("app.modules.knowledge.ingestion_service._ingestion_view", ingestion_view)

    await service.confirm_upload(
        _principal(),
        "tenant_test",
        source.id,
        KnowledgeSourceConfirmRequest(staging_key=staging_key),
    )

    queued_document, version, job = session.add_all.call_args.args[0]
    assert queued_document is document
    assert isinstance(version, KnowledgeDocumentVersion)
    assert version.version == 2
    assert version.source_id == source.id
    assert version.status == "processing"
    assert job.action == "replace"
    assert document.status == "active"


@pytest.mark.asyncio
async def test_retry_confirmation_uses_the_server_owned_staging_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = InMemoryObjectStorage()
    service, _session = _service(storage)
    source = _upload_source()
    staging_key = cast(str, source.staging_key)
    storage.objects[staging_key] = ObjectData(
        content=b"Release runbook", content_type="text/markdown"
    )
    service.repository = cast(
        KnowledgeIngestionRepository,
        SimpleNamespace(get_source_for_update=AsyncMock(return_value=source)),
    )
    expected = cast(KnowledgeIngestionView, SimpleNamespace(id="job_test"))
    confirm = AsyncMock(return_value=expected)
    monkeypatch.setattr(service, "_confirm_staged_source", confirm, raising=False)

    result = await service.retry_upload_confirmation(_principal(), "tenant_test", source.id)

    assert result is expected
    confirm.assert_awaited_once_with(_principal(), "tenant_test", source, staging_key)


@pytest.mark.asyncio
async def test_retry_confirmation_recovers_an_existing_matching_canonical_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = InMemoryObjectStorage()
    storage.reject_existing_move = True
    service, _session = _service(storage)
    source = _upload_source()
    staging_key = cast(str, source.staging_key)
    content = b"Release runbook"
    canonical_key = "knowledge/tenant_test/space_test/source_test/source.md"
    storage.objects[staging_key] = ObjectData(content=content, content_type="text/markdown")
    storage.objects[canonical_key] = ObjectData(content=content, content_type="text/markdown")
    service.repository = cast(
        KnowledgeIngestionRepository,
        SimpleNamespace(get_source_for_update=AsyncMock(return_value=source)),
    )

    def ingestion_view(
        _job: KnowledgeIngestionJob, _document: KnowledgeDocument
    ) -> KnowledgeIngestionView:
        return cast(KnowledgeIngestionView, SimpleNamespace())

    monkeypatch.setattr(
        "app.modules.knowledge.ingestion_service._ingestion_view",
        ingestion_view,
    )

    await service.retry_upload_confirmation(_principal(), "tenant_test", source.id)

    assert source.status == "queued"
    assert source.object_key == canonical_key
    assert staging_key not in storage.objects


@pytest.mark.asyncio
async def test_retry_confirmation_returns_a_safe_error_when_object_storage_is_unavailable() -> None:
    storage = InMemoryObjectStorage()
    storage.move_error = ObjectStorageOperationError("move", status_code=503)
    service, _session = _service(storage)
    source = _upload_source()
    staging_key = cast(str, source.staging_key)
    storage.objects[staging_key] = ObjectData(
        content=b"Release runbook", content_type="text/markdown"
    )
    service.repository = cast(
        KnowledgeIngestionRepository,
        SimpleNamespace(get_source_for_update=AsyncMock(return_value=source)),
    )

    with pytest.raises(AppError) as error:
        await service.retry_upload_confirmation(_principal(), "tenant_test", source.id)

    assert error.value.code == "KNOWLEDGE_SOURCE_UNAVAILABLE"
    assert error.value.status_code == 503
    assert source.status == "staging"
    assert staging_key in storage.objects


@pytest.mark.asyncio
async def test_retry_confirmation_abandons_when_staging_object_is_missing() -> None:
    storage = InMemoryObjectStorage()
    service, session = _service(storage)
    source = _upload_source()
    delete_source = AsyncMock()
    service.repository = cast(
        KnowledgeIngestionRepository,
        SimpleNamespace(
            get_source_for_update=AsyncMock(return_value=source),
            delete_source=delete_source,
        ),
    )

    with pytest.raises(AppError) as error:
        await service.retry_upload_confirmation(_principal(), "tenant_test", source.id)

    assert error.value.code == "KNOWLEDGE_UPLOAD_NOT_FOUND"
    assert error.value.status_code == 404
    assert delete_source.await_count == 1
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_retry_confirmation_abandons_when_promotion_reports_missing_object() -> None:
    storage = InMemoryObjectStorage()
    storage.move_error = ObjectStorageOperationError("management", status_code=612)
    service, session = _service(storage)
    source = _upload_source()
    staging_key = cast(str, source.staging_key)
    storage.objects[staging_key] = ObjectData(
        content=b"Release runbook", content_type="text/markdown"
    )
    delete_source = AsyncMock()
    service.repository = cast(
        KnowledgeIngestionRepository,
        SimpleNamespace(
            get_source_for_update=AsyncMock(return_value=source),
            delete_source=delete_source,
        ),
    )

    with pytest.raises(AppError) as error:
        await service.retry_upload_confirmation(_principal(), "tenant_test", source.id)

    assert error.value.code == "KNOWLEDGE_UPLOAD_NOT_FOUND"
    assert error.value.status_code == 404
    assert staging_key not in storage.objects
    assert delete_source.await_count == 1
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_cleanup_staging_source_removes_only_the_disposable_object() -> None:
    storage = InMemoryObjectStorage()
    service, session = _service(storage)
    source = _upload_source()
    staging_key = cast(str, source.staging_key)
    storage.objects[staging_key] = ObjectData(
        content=b"Release runbook", content_type="text/markdown"
    )
    delete_source = AsyncMock()
    service.repository = cast(
        KnowledgeIngestionRepository,
        SimpleNamespace(
            get_source_for_update=AsyncMock(return_value=source),
            delete_source=delete_source,
        ),
    )

    await service.cleanup_staging_source(_principal(), "tenant_test", source.id)

    assert staging_key not in storage.objects
    assert delete_source.await_count == 1
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_cleanup_rejects_a_source_that_has_already_been_confirmed() -> None:
    service, _session = _service(InMemoryObjectStorage())
    source = _upload_source(status="queued", staging_key=None)
    service.repository = cast(
        KnowledgeIngestionRepository,
        SimpleNamespace(get_source_for_update=AsyncMock(return_value=source)),
    )

    with pytest.raises(AppError) as error:
        await service.cleanup_staging_source(_principal(), "tenant_test", source.id)

    assert error.value.code == "KNOWLEDGE_SOURCE_STATE_INVALID"
    assert error.value.status_code == 409
