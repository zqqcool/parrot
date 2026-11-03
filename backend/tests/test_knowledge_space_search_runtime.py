from __future__ import annotations

import base64
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest

from app.core.config import load_app_config
from app.infrastructure.credential_cipher import CredentialCipher
from app.infrastructure.db.session import DatabaseManager
from app.modules.embedding_configs.models import EmbeddingConfig
from app.modules.knowledge.runtime_helpers import lexical_query_variants
from app.modules.knowledge.runtime_repository import KnowledgeEvidenceRow
from app.modules.knowledge.runtime_types import KnowledgeRuntimeContext
from app.modules.knowledge.space_search_runtime import KnowledgeSpaceSearchRuntime

ROOT = Path(__file__).resolve().parents[1]


def test_lexical_query_variants_preserves_exact_query_before_latin_fallback() -> None:
    assert lexical_query_variants("parrot是什么") == ("parrot是什么", "parrot")
    assert lexical_query_variants("release policy") == ("release policy",)


@pytest.mark.asyncio
async def test_space_search_fuses_vector_and_lexical_results_when_vector_is_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(vector_ready=True)
    space = _space()
    space.min_vector_score = 0.85
    embedding = _embedding()
    rows = _rows()

    class FakeEmbedding:
        def __init__(self, *_args: object) -> None:
            pass

        async def embed(self, values: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
            assert values == ("release policy",)
            return ((0.1, 0.2),)

    class FakeVectorStore:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        async def search_scored(self, *_args: object) -> tuple[SimpleNamespace, ...]:
            return (
                SimpleNamespace(chunk_id="chunk_shared", score=0.9),
                SimpleNamespace(chunk_id="chunk_vector", score=0.8),
            )

    monkeypatch.setattr("app.modules.knowledge.runtime.ConfiguredKnowledgeEmbedding", FakeEmbedding)
    monkeypatch.setattr("app.modules.knowledge.runtime.MilvusKnowledgeVectorStore", FakeVectorStore)
    runtime = KnowledgeSpaceSearchRuntime(
        cast(DatabaseManager, SimpleNamespace()), settings=settings, cipher=_cipher()
    )
    monkeypatch.setattr(
        runtime,
        "_configured_profiles",
        AsyncMock(return_value=((space,), {embedding.id: embedding}, {})),
    )
    monkeypatch.setattr(
        runtime,
        "_lexical_candidates_in_space",
        AsyncMock(return_value=("chunk_bm25", "chunk_shared")),
    )

    async def authorized(
        _context: KnowledgeRuntimeContext, chunk_ids: tuple[str, ...]
    ) -> list[KnowledgeEvidenceRow]:
        return [cast(KnowledgeEvidenceRow, rows[item]) for item in chunk_ids]

    monkeypatch.setattr(
        runtime,
        "_authorized_evidence",
        AsyncMock(side_effect=authorized),
    )

    result = await runtime.search("tenant_test", space.id, "release policy", 2)

    assert result.retrieval_method == "hybrid"
    assert result.status == "ok"
    assert result.citation_ids == ("chunk_shared", "chunk_bm25")
    assert "chunk_vector" not in result.citation_ids
    assert result.items[0].score == pytest.approx(1 / 61)
    assert result.items[0].match_sources == ("lexical", "vector")
    assert result.items[0].vector_score == pytest.approx(0.9)
    assert result.items[1].match_sources == ("lexical",)
    assert result.items[1].vector_score is None
    assert result.items[0].document_id == "document_shared"
    assert result.items[0].content_chars == len("Evidence for chunk_shared")


@pytest.mark.asyncio
async def test_space_search_reports_an_unavailable_vector_runtime_and_keeps_lexical_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    space = _space()
    rows = _rows()
    runtime = KnowledgeSpaceSearchRuntime(
        cast(DatabaseManager, SimpleNamespace()),
        settings=_settings(vector_ready=False),
        cipher=_cipher(),
    )
    monkeypatch.setattr(
        runtime,
        "_configured_profiles",
        AsyncMock(return_value=((space,), {"embedding_test": _embedding()}, {})),
    )
    monkeypatch.setattr(
        runtime,
        "_lexical_candidates_in_space",
        AsyncMock(return_value=("chunk_bm25",)),
    )
    monkeypatch.setattr(
        runtime,
        "_authorized_evidence",
        AsyncMock(return_value=[rows["chunk_bm25"]]),
    )

    result = await runtime.search("tenant_test", space.id, "release policy", 20)

    assert result.retrieval_method == "lexical_fallback"
    assert result.status == "degraded"
    assert result.citation_ids == ("chunk_bm25",)
    assert result.items[0].degradation_reason == "vector_runtime_unavailable"


def _settings(*, vector_ready: bool):
    settings = load_app_config(ROOT / "config" / "dev.toml")
    return settings.model_copy(
        update={
            "knowledge_credentials": settings.knowledge_credentials.model_copy(
                update={"values": {"milvus-root-token": "test-token"} if vector_ready else {}}
            )
        }
    )


def _space() -> SimpleNamespace:
    return SimpleNamespace(
        id="space_test",
        embedding_config_id="embedding_test",
        embedding_config_provider="openai_compatible",
        embedding_config_model="embedding-model",
        embedding_config_base_url="http://127.0.0.1:11434/v1",
        embedding_config_dimension=2,
        embedding_config_version=1,
        candidate_top_k=20,
        min_vector_score=None,
        rerank_enabled=False,
        reranker_config_id=None,
        retrieval_index_status="ready",
    )


def _embedding() -> EmbeddingConfig:
    return EmbeddingConfig(
        id="embedding_test",
        tenant_id="tenant_test",
        name="Embedding",
        provider="openai_compatible",
        model="embedding-model",
        base_url="http://127.0.0.1:11434/v1",
        credential_envelope="v1.encrypted",
        embedding_dimension=2,
        configuration_version=1,
        status="active",
    )


def _rows() -> dict[str, tuple[SimpleNamespace, SimpleNamespace, SimpleNamespace]]:
    return {
        item: (
            SimpleNamespace(
                id=item,
                space_id="space_test",
                citation_anchor=f"anchor-{item}",
                content=f"Evidence for {item}",
                group_id=None,
                ordinal=1,
                page_kind=None,
                slide_no=None,
            ),
            SimpleNamespace(id=f"document_{item.removeprefix('chunk_')}", title="Release"),
            SimpleNamespace(id=f"version_{item}"),
        )
        for item in ("chunk_bm25", "chunk_shared", "chunk_vector")
    }


def _cipher() -> CredentialCipher:
    return CredentialCipher(base64.urlsafe_b64encode(b"0" * 32).decode().rstrip("="))
