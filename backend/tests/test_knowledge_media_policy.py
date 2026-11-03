from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import Clock
from app.core.object_storage import (
    ObjectData,
    ObjectStorageOperationError,
    ObjectStoragePort,
)
from app.modules.knowledge import ingestion_publish
from app.modules.knowledge.extraction.types import (
    ExtractedBlock,
    ExtractedDocument,
    ExtractedMedia,
)
from app.modules.knowledge.models import (
    KnowledgeDocument,
    KnowledgeDocumentVersion,
    KnowledgeIngestionJob,
)


@pytest.mark.asyncio
async def test_publish_skips_unsupported_office_media_before_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, ExtractedDocument] = {}

    async def publish_structured(_session: object, **kwargs: object) -> tuple[str, int]:
        extracted = cast(ExtractedDocument, kwargs["extracted"])
        observed["extracted"] = extracted
        return "CRM index text", len(extracted.media)

    monkeypatch.setattr(ingestion_publish, "_clear_version_children", AsyncMock())
    monkeypatch.setattr(ingestion_publish, "_publish_structured", publish_structured)
    monkeypatch.setattr(ingestion_publish, "enqueue_vector_job", AsyncMock())

    source = SimpleNamespace(id="source_test", status="processing", title="CRM 三期")
    session = cast(AsyncSession, SimpleNamespace(scalar=AsyncMock(return_value=source)))
    document = KnowledgeDocument(
        id="document_test",
        tenant_id="tenant_test",
        space_id="space_test",
        title="CRM 三期",
        title_key="crm 三期",
        status="processing",
        created_by_user_id="user_test",
    )
    version = KnowledgeDocumentVersion(
        id="version_test",
        tenant_id="tenant_test",
        document_id=document.id,
        source_id="source_test",
        version=1,
        content_sha256="a" * 64,
        created_by_user_id="user_test",
        content="",
    )
    job = KnowledgeIngestionJob(
        id="job_test",
        tenant_id="tenant_test",
        source_id="source_test",
        document_version_id=version.id,
        status="running",
        attempts=1,
        lease_owner="worker",
        lease_until=datetime.now(UTC),
    )
    extracted = ExtractedDocument(
        format_profile="pptx",
        extractor_name="pptx_document",
        extractor_version="1",
        blocks=(ExtractedBlock(index_text="CRM 三期", slide_no=147),),
        media=(
            ExtractedMedia(
                asset_kind="embedded",
                content=b"\x89PNG\r\n\x1a\n",
                content_type="image/png",
                slide_no=146,
                ordinal_in_group=1,
            ),
            ExtractedMedia(
                asset_kind="embedded",
                content=b"\x01\x00\x00\x00wmf",
                content_type="image/x-wmf",
                slide_no=147,
                ordinal_in_group=1,
            ),
        ),
    )
    clock = cast(Clock, SimpleNamespace(now=lambda: datetime.now(UTC)))

    await ingestion_publish.publish_extracted_document(
        session,
        tenant_id="tenant_test",
        source_id="source_test",
        job=job,
        version=version,
        document=document,
        extracted=extracted,
        clock=clock,
        dispatcher=None,
        object_storage=None,
    )

    sanitized = observed["extracted"]
    assert tuple(item.content_type for item in sanitized.media) == ("image/png",)
    assert sanitized.skipped_media_count == 1
    assert sanitized.warnings == ("unsupported_media_skipped",)
    assert version.media_count == 1
    assert version.skipped_media_count == 1


@pytest.mark.asyncio
async def test_media_persistence_recovers_matching_existing_object() -> None:
    content = b"\x89PNG\r\n\x1a\n"
    write = AsyncMock(side_effect=ObjectStorageOperationError("write", status_code=614))
    read = AsyncMock(return_value=ObjectData(content=content, content_type="image/png"))
    add = Mock()
    storage = cast(
        ObjectStoragePort,
        SimpleNamespace(
            write=write,
            read=read,
        ),
    )
    session = cast(AsyncSession, SimpleNamespace(add=add))

    await ingestion_publish._persist_media(  # pyright: ignore[reportPrivateUsage]
        session,
        tenant_id="tenant_test",
        space_id="space_test",
        version_id="version_test",
        group_ids={},
        media=(
            ExtractedMedia(
                asset_kind="embedded",
                content=content,
                content_type="image/png",
                slide_no=1,
                ordinal_in_group=1,
            ),
        ),
        object_storage=storage,
    )

    read.assert_awaited_once()
    add.assert_called_once()


@pytest.mark.asyncio
async def test_media_persistence_rejects_different_existing_object() -> None:
    write = AsyncMock(side_effect=ObjectStorageOperationError("write", status_code=614))
    read = AsyncMock(
        return_value=ObjectData(content=b"different-content", content_type="image/png")
    )
    storage = cast(ObjectStoragePort, SimpleNamespace(write=write, read=read))
    session = cast(AsyncSession, SimpleNamespace(add=Mock()))

    with pytest.raises(ObjectStorageOperationError) as error:
        await ingestion_publish._persist_media(  # pyright: ignore[reportPrivateUsage]
            session,
            tenant_id="tenant_test",
            space_id="space_test",
            version_id="version_test",
            group_ids={},
            media=(
                ExtractedMedia(
                    asset_kind="embedded",
                    content=b"\x89PNG\r\n\x1a\n",
                    content_type="image/png",
                    slide_no=1,
                    ordinal_in_group=1,
                ),
            ),
            object_storage=storage,
        )

    assert error.value.status_code == 614
