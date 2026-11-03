from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.infrastructure.db.session import DatabaseManager
from app.modules.iam.schemas import PrincipalContext
from app.modules.knowledge.citation_service import KnowledgeCitationService
from app.modules.knowledge.repository import KnowledgeRepository


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


def citation_service(*, content: str, has_access: bool) -> KnowledgeCitationService:
    instance = KnowledgeCitationService(
        cast(AsyncSession, SimpleNamespace()),
        cast(DatabaseManager, SimpleNamespace(set_tenant=AsyncMock())),
    )
    instance.repository = cast(
        KnowledgeRepository,
        SimpleNamespace(
            citation=AsyncMock(
                return_value=(
                    SimpleNamespace(
                        id="chunk_test",
                        space_id="space_test",
                        citation_anchor="chunk-1",
                        content=content,
                        slide_no=None,
                    ),
                    SimpleNamespace(id="document_test", title="Release policy"),
                    SimpleNamespace(id="version_test"),
                )
            ),
            user_has_access=AsyncMock(return_value=has_access),
        ),
    )
    instance._media_refs = AsyncMock(return_value=())  # type: ignore[method-assign]
    return instance


@pytest.mark.asyncio
async def test_citation_expansion_rechecks_current_space_access() -> None:
    instance = citation_service(content="Private release policy.", has_access=False)

    with pytest.raises(AppError) as error:
        await instance.expand(principal("knowledge.query"), "tenant_test", "chunk_test")

    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_citation_expansion_returns_the_complete_immutable_chunk() -> None:
    content = "# Release policy\n\n" + ("完整内容。" * 1_200)
    instance = citation_service(content=content, has_access=True)

    result = await instance.expand(principal("knowledge.query"), "tenant_test", "chunk_test")

    assert result.content == content
    assert result.content_chars == len(content)
    assert len(result.excerpt) == 4_000
    assert result.excerpt.endswith("…")
