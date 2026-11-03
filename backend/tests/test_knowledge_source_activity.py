from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.session import DatabaseManager
from app.modules.iam.schemas import PrincipalContext, UserReference
from app.modules.iam.user_references import UserReferenceResolver
from app.modules.knowledge.access import KnowledgeAccessPolicy
from app.modules.knowledge.models import KnowledgeSource
from app.modules.knowledge.source_activity_repository import (
    KnowledgeSourceActivityRecord,
    KnowledgeSourceActivityRepository,
)
from app.modules.knowledge.source_activity_service import KnowledgeSourceActivityService


def _principal() -> PrincipalContext:
    return PrincipalContext(
        tenant_id="tenant_test",
        subject_id="user_test",
        username="operator",
        display_name="Operator",
        permissions=("knowledge.documents.read",),
        tenants=(),
        must_change_password=False,
        request_id="req_test",
    )


def _staging_source() -> KnowledgeSource:
    now = datetime.now(UTC)
    return KnowledgeSource(
        id="source_staging",
        tenant_id="tenant_test",
        space_id="space_test",
        source_kind="upload",
        title="Release runbook",
        original_filename="release.pdf",
        content_type="application/pdf",
        declared_size_bytes=1024,
        staging_key="staging/knowledge/source_staging/upload.pdf",
        status="staging",
        created_by_user_id="user_test",
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_source_activity_exposes_staging_upload_without_document() -> None:
    service = KnowledgeSourceActivityService(
        cast(AsyncSession, SimpleNamespace()),
        cast(DatabaseManager, SimpleNamespace()),
    )
    service.access_policy = cast(
        KnowledgeAccessPolicy,
        SimpleNamespace(require_space=AsyncMock(return_value=SimpleNamespace())),
    )
    service.repository = cast(
        KnowledgeSourceActivityRepository,
        SimpleNamespace(
            list_for_space=AsyncMock(
                return_value=(
                    (
                        KnowledgeSourceActivityRecord(
                            source=_staging_source(),
                            document_id=None,
                            attempts=0,
                            error_code=None,
                            created_by_user_id="user_test",
                            created_by_display_name="Operator",
                        ),
                    ),
                    1,
                )
            )
        ),
    )
    service.user_references = cast(
        UserReferenceResolver,
        SimpleNamespace(
            resolve=AsyncMock(
                return_value={
                    "user_test": UserReference(
                        id="user_test", display_name="Operator", avatar_present=False
                    )
                }
            ),
        ),
    )

    page = await service.list_for_space(
        _principal(),
        "tenant_test",
        "space_test",
        page=1,
        page_size=10,
    )

    assert page.total == 1
    assert page.items[0].status == "staging"
    assert page.items[0].staging_expires_at is not None
    assert page.items[0].document_id is None
    assert page.items[0].attempts == 0
    assert page.items[0].original_filename == "release.pdf"
    assert page.items[0].created_by_user is not None
    assert page.items[0].created_by_user.display_name == "Operator"
