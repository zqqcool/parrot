from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import AppConfig
from app.infrastructure.credential_cipher import CredentialCipher
from app.infrastructure.db.session import DatabaseManager
from app.modules.agents.ports import AgentCatalogPort
from app.modules.iam.schemas import PrincipalContext
from app.modules.knowledge.models import KnowledgeSpace
from app.modules.knowledge.runtime_types import KnowledgeEvidenceBundle, KnowledgeEvidenceItem
from app.modules.knowledge.service import KnowledgeService


@pytest.mark.asyncio
async def test_space_search_exposes_runtime_rank_and_original_chunk_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = SimpleNamespace(
        get_space=AsyncMock(return_value=_space()),
        user_has_access=AsyncMock(return_value=True),
        search=AsyncMock(
            return_value=(
                (
                    SimpleNamespace(
                        id="chunk_test",
                        content="Release requires approval.",
                        citation_anchor="chunk-1",
                    ),
                    SimpleNamespace(id="document_test", title="Release process"),
                    SimpleNamespace(id="version_test"),
                    0.375,
                ),
            )
        ),
    )
    instance = _service(repository)
    runtime = SimpleNamespace(
        search=AsyncMock(return_value=_result("Release requires approval.", 0.375))
    )

    def runtime_factory(*_args: object, **_kwargs: object) -> SimpleNamespace:
        return runtime

    monkeypatch.setattr(
        "app.modules.knowledge.service.KnowledgeSpaceSearchRuntime",
        runtime_factory,
    )

    result = await instance.search(_principal(), "tenant_test", "space_test", "release approval")

    assert len(result) == 1
    assert result[0].score == 0.375
    assert result[0].content_chars == len("Release requires approval.")
    assert result[0].excerpt == "Release requires approval."
    assert result[0].excerpt_truncated is False
    assert result[0].match_sources == ("lexical", "vector")
    assert result[0].vector_score == pytest.approx(0.875)
    runtime.search.assert_awaited_once_with("tenant_test", "space_test", "release approval", 20)


@pytest.mark.asyncio
async def test_space_search_marks_a_bounded_excerpt_as_truncated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    content = "x" * 1_200
    repository = SimpleNamespace(
        get_space=AsyncMock(return_value=_space()),
        user_has_access=AsyncMock(return_value=True),
        search=AsyncMock(
            return_value=(
                (
                    SimpleNamespace(id="chunk_test", content=content, citation_anchor="chunk-1"),
                    SimpleNamespace(id="document_test", title="Release process"),
                    SimpleNamespace(id="version_test"),
                    0.25,
                ),
            )
        ),
    )

    runtime = SimpleNamespace(search=AsyncMock(return_value=_result(content, 0.25)))

    def runtime_factory(*_args: object, **_kwargs: object) -> SimpleNamespace:
        return runtime

    monkeypatch.setattr(
        "app.modules.knowledge.service.KnowledgeSpaceSearchRuntime",
        runtime_factory,
    )
    result = await _service(repository).search(
        _principal(), "tenant_test", "space_test", "release approval"
    )

    assert result[0].content_chars == 1_200
    assert len(result[0].excerpt) == 800
    assert result[0].excerpt.endswith("…")
    assert result[0].excerpt_truncated is True


def _principal() -> PrincipalContext:
    return PrincipalContext(
        tenant_id="tenant_test",
        subject_id="user_test",
        username="operator",
        display_name="Operator",
        permissions=("knowledge.query",),
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
        chunk_size_chars=4_000,
        chunk_overlap_chars=200,
        candidate_top_k=20,
        access_revision=4,
        created_by_user_id="user_test",
        created_at=now,
        updated_at=now,
    )


def _result(content: str, score: float) -> KnowledgeEvidenceBundle:
    return KnowledgeEvidenceBundle(
        status="ok",
        retrieval_method="hybrid",
        items=(
            KnowledgeEvidenceItem(
                citation_id="chunk_test",
                document_id="document_test",
                document_version_id="version_test",
                title="Release process",
                citation_anchor="chunk-1",
                space_id="space_test",
                retrieval_method="hybrid",
                score=score,
                excerpt=content[:799].rstrip() + ("…" if len(content) > 800 else ""),
                content_chars=len(content),
                match_sources=("lexical", "vector"),
                vector_score=0.875,
            ),
        ),
    )


def _service(repository: object) -> KnowledgeService:
    session = SimpleNamespace(
        add=Mock(),
        add_all=Mock(),
        execute=AsyncMock(),
        flush=AsyncMock(),
    )
    instance = KnowledgeService(
        cast(AsyncSession, session),
        cast(DatabaseManager, SimpleNamespace(set_tenant=AsyncMock())),
        cast(AgentCatalogPort, SimpleNamespace(exists=AsyncMock(return_value=True))),
        settings=cast(
            AppConfig,
            SimpleNamespace(
                knowledge=SimpleNamespace(
                    vector=SimpleNamespace(candidate_multiplier=4, reciprocal_rank_constant=60)
                )
            ),
        ),
        cipher=cast(CredentialCipher, SimpleNamespace()),
    )
    instance.repository = repository  # type: ignore[assignment]
    return instance
