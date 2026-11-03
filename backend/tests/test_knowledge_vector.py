from __future__ import annotations

import base64
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import load_app_config
from app.infrastructure.credential_cipher import CredentialCipher
from app.infrastructure.db.session import DatabaseManager
from app.modules.embedding_configs.models import EmbeddingConfig
from app.modules.knowledge.embedding import KnowledgeEmbeddingPort
from app.modules.knowledge.models import KnowledgeSpace
from app.modules.knowledge.runtime import (
    KnowledgeRuntimeContext,
    SqlKnowledgeRuntime,
    reciprocal_rank_fusion,
)
from app.modules.knowledge.semantic_search import (
    KnowledgeSemanticSearch,
    KnowledgeSemanticSearchPort,
)
from app.modules.knowledge.vector_store import (
    KnowledgeVectorSearchScope,
    KnowledgeVectorStore,
    _chunk_ids,  # pyright: ignore[reportPrivateUsage]
    knowledge_vector_scope_filter,
)

ROOT = Path(__file__).resolve().parents[1]


def test_reciprocal_rank_fusion_combines_lexical_and_semantic_rankings() -> None:
    result = reciprocal_rank_fusion(
        ("chunk_a", "chunk_b"),
        ("chunk_b", "chunk_c"),
        constant=60,
        limit=3,
    )

    assert result == ("chunk_b", "chunk_a", "chunk_c")


def test_vector_scope_filter_is_tenant_and_bound_space_scoped() -> None:
    result = knowledge_vector_scope_filter(
        KnowledgeVectorSearchScope(tenant_id='tenant_"quoted', space_ids=("space_a", "space_b"))
    )

    assert 'tenant_id == "tenant_\\"quoted"' in result
    assert 'space_id == "space_a"' in result
    assert 'space_id == "space_b"' in result


def test_milvus_results_read_output_fields_from_entity() -> None:
    result = _chunk_ids([[{"id": "vector_1", "distance": 0.1, "entity": {"chunk_id": "chunk_1"}}]])

    assert result == ("chunk_1",)


@pytest.mark.asyncio
async def test_semantic_search_embeds_one_query_and_preserves_relational_scope() -> None:
    embeddings = SimpleNamespace(embed=AsyncMock(return_value=((0.1, 0.2),)))
    vectors = SimpleNamespace(search=AsyncMock(return_value=("chunk_a",)))
    search = KnowledgeSemanticSearch(
        cast(KnowledgeEmbeddingPort, embeddings), cast(KnowledgeVectorStore, vectors)
    )

    result = await search.search("tenant_test", ("space_a",), "release policy", 8)

    assert result == ("chunk_a",)
    embeddings.embed.assert_awaited_once_with(("release policy",))
    scope = vectors.search.await_args.args[1]
    assert scope == KnowledgeVectorSearchScope("tenant_test", ("space_a",))


@pytest.mark.asyncio
async def test_hybrid_runtime_reauthorizes_all_candidates_after_vector_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = {
        chunk_id: (
            SimpleNamespace(
                id=chunk_id,
                citation_anchor=f"anchor-{chunk_id}",
                content=f"Evidence for {chunk_id}",
                group_id=None,
                ordinal=1,
                page_kind=None,
                slide_no=None,
            ),
            SimpleNamespace(title=f"Document {chunk_id}"),
            SimpleNamespace(id=f"version_{chunk_id}"),
        )
        for chunk_id in ("chunk_a", "chunk_b", "chunk_c")
    }

    async def authorized_candidates(
        _tenant_id: str, _agent_id: str, chunk_ids: tuple[str, ...]
    ) -> list[tuple[object, object, object]]:
        return [rows[item] for item in chunk_ids]

    repository = SimpleNamespace(
        active_space_ids=AsyncMock(return_value=("space_bound",)),
        lexical_search=AsyncMock(return_value=[rows["chunk_a"], rows["chunk_b"]]),
        authorized_candidates=AsyncMock(side_effect=authorized_candidates),
    )

    def repository_factory(_session: AsyncSession) -> SimpleNamespace:
        return repository

    session_object = object()

    @asynccontextmanager
    async def session():
        yield session_object

    database = SimpleNamespace(session=session, set_tenant=AsyncMock())
    semantic = SimpleNamespace(search=AsyncMock(return_value=("chunk_b", "chunk_c")))
    monkeypatch.setattr(
        "app.modules.knowledge.runtime.KnowledgeRuntimeRepository", repository_factory
    )
    runtime = SqlKnowledgeRuntime(
        cast(DatabaseManager, database),
        cast(KnowledgeSemanticSearchPort, semantic),
        retrieval_mode="hybrid",
    )

    result = await runtime.retrieve(
        KnowledgeRuntimeContext(
            tenant_id="tenant_test", agent_id="agent_test", query="release policy", limit=3
        )
    )

    assert result.status == "ok"
    assert result.retrieval_method == "hybrid"
    assert result.citation_ids == ("chunk_b", "chunk_a", "chunk_c")
    semantic.search.assert_awaited_once_with("tenant_test", ("space_bound",), "release policy", 12)
    repository.authorized_candidates.assert_awaited_once_with(
        "tenant_test", "agent_test", ("chunk_b", "chunk_a", "chunk_c")
    )


@pytest.mark.asyncio
async def test_configured_runtime_falls_back_only_for_the_space_with_vector_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _vector_settings()
    broken_space = cast(
        object,
        SimpleNamespace(
            id="space_broken",
            embedding_config_id="embedding_broken",
            embedding_config_provider="openai_compatible",
            embedding_config_model="embedding-model",
            embedding_config_base_url="http://127.0.0.1:11434/v1",
            embedding_config_dimension=2,
            embedding_config_version=1,
            candidate_top_k=20,
            min_vector_score=None,
            rerank_enabled=False,
            reranker_config_id=None,
        ),
    )
    lexical_space = cast(
        object,
        SimpleNamespace(
            id="space_lexical",
            embedding_config_id=None,
            candidate_top_k=20,
            min_vector_score=None,
            rerank_enabled=False,
            reranker_config_id=None,
        ),
    )
    embedding = EmbeddingConfig(
        id="embedding_broken",
        tenant_id="tenant_test",
        name="Broken embedding",
        provider="openai_compatible",
        model="embedding-model",
        base_url="http://127.0.0.1:11434/v1",
        credential_envelope="v1.encrypted",
        embedding_dimension=2,
        configuration_version=1,
        status="active",
    )

    class BrokenEmbedding:
        def __init__(self, *_args: object) -> None:
            pass

        async def embed(self, _values: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
            raise RuntimeError("provider unavailable")

    monkeypatch.setattr(
        "app.modules.knowledge.runtime.ConfiguredKnowledgeEmbedding", BrokenEmbedding
    )
    runtime = SqlKnowledgeRuntime(
        cast(DatabaseManager, SimpleNamespace()),
        settings=settings,
        cipher=CredentialCipher(_cipher_key()),
    )
    monkeypatch.setattr(
        runtime,
        "_configured_profiles",
        AsyncMock(return_value=((broken_space, lexical_space), {embedding.id: embedding}, {})),
    )
    monkeypatch.setattr(
        runtime,
        "_lexical_candidates_in_space",
        AsyncMock(side_effect=(("chunk_broken",), ("chunk_lexical",))),
    )
    monkeypatch.setattr(runtime, "_load_merge_settings", AsyncMock(return_value=None))

    selection, _embed_ms, _space_count = await runtime._configured_candidates(  # pyright: ignore[reportPrivateUsage]
        KnowledgeRuntimeContext("tenant_test", "agent_test", "release policy"), 6
    )

    assert selection.retrieval_method == "lexical_fallback"
    assert selection.provenance_by_space["space_broken"].retrieval_method == "lexical_fallback"
    assert (
        selection.provenance_by_space["space_broken"].degradation_reason
        == "embedding_or_vector_service_unavailable"
    )
    assert selection.provenance_by_space["space_lexical"].retrieval_method == "lexical"
    assert "chunk_lexical" in selection.ranked_ids


@pytest.mark.asyncio
async def test_agent_runtime_reports_unavailable_vector_runtime_and_keeps_keyword_retrieval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured = load_app_config(ROOT / "config" / "dev.toml")
    settings = configured.model_copy(
        update={
            "knowledge": configured.knowledge.model_copy(
                update={"vector": configured.knowledge.vector.model_copy(update={"uri": None})}
            )
        }
    )
    space = cast(
        KnowledgeSpace,
        SimpleNamespace(
            id="space_test",
            embedding_config_id="embedding_test",
            candidate_top_k=20,
            min_vector_score=None,
            rerank_enabled=False,
            reranker_config_id=None,
            retrieval_index_status="ready",
        ),
    )
    embedding = EmbeddingConfig(
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
    row = cast(
        tuple[object, object, object],
        (
            SimpleNamespace(
                id="chunk_keyword",
                space_id=space.id,
                citation_anchor="chunk-1",
                content="Parrot knowledge",
                group_id=None,
                ordinal=1,
                page_kind=None,
                slide_no=None,
            ),
            SimpleNamespace(id="document_test", title="Knowledge"),
            SimpleNamespace(id="version_test"),
        ),
    )
    runtime = SqlKnowledgeRuntime(
        cast(DatabaseManager, SimpleNamespace()),
        settings=settings,
        cipher=CredentialCipher(_cipher_key()),
    )
    monkeypatch.setattr(
        runtime,
        "_configured_profiles",
        AsyncMock(return_value=((space,), {embedding.id: embedding}, {})),
    )
    monkeypatch.setattr(
        runtime,
        "_lexical_candidates_in_space",
        AsyncMock(return_value=("chunk_keyword",)),
    )
    monkeypatch.setattr(runtime, "_authorized_evidence", AsyncMock(return_value=[row]))

    result = await runtime.retrieve(
        KnowledgeRuntimeContext("tenant_test", "agent_test", "parrot是什么")
    )

    assert result.status == "degraded"
    assert result.retrieval_method == "lexical_fallback"
    assert result.citation_ids == ("chunk_keyword",)
    assert result.items[0].degradation_reason == "vector_runtime_unavailable"


def test_disabled_embedding_profile_remains_usable_when_its_snapshot_matches() -> None:
    space = cast(
        KnowledgeSpace,
        SimpleNamespace(
            embedding_config_id="embedding_test",
            embedding_config_provider="openai_compatible",
            embedding_config_model="embedding-model",
            embedding_config_base_url="http://127.0.0.1:11434/v1",
            embedding_config_dimension=1024,
            embedding_config_version=1,
        ),
    )
    embedding = EmbeddingConfig(
        id="embedding_test",
        tenant_id="tenant_test",
        name="Archived embedding",
        provider="openai_compatible",
        model="embedding-model",
        base_url="http://127.0.0.1:11434/v1",
        credential_envelope="v1.encrypted",
        embedding_dimension=1024,
        configuration_version=1,
        status="disabled",
    )
    settings = _vector_settings()
    runtime = SqlKnowledgeRuntime(cast(DatabaseManager, SimpleNamespace()), settings=settings)

    assert runtime._semantic_skip_reason(space, embedding) is None  # pyright: ignore[reportPrivateUsage]
    space.embedding_config_dimension = 768
    assert (
        runtime._semantic_skip_reason(  # pyright: ignore[reportPrivateUsage]
            space, embedding
        )
        == "embedding_config_snapshot_mismatch"
    )


def _cipher_key() -> str:
    return base64.urlsafe_b64encode(b"0" * 32).decode().rstrip("=")


def _vector_settings():
    settings = load_app_config(ROOT / "config" / "dev.toml")
    return settings.model_copy(
        update={
            "knowledge_credentials": settings.knowledge_credentials.model_copy(
                update={"values": {"milvus-root-token": "test-token"}}
            )
        }
    )
