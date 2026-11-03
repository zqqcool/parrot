# pyright: reportPrivateUsage=false

from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.infrastructure.db.session import DatabaseManager
from app.modules.iam.schemas import PrincipalContext
from app.modules.knowledge.merge_models import KnowledgeMergeSettings
from app.modules.knowledge.merge_schemas import KnowledgeMergeSettingsUpdateRequest
from app.modules.knowledge.merge_settings import default_merge_settings_view, merge_settings_view
from app.modules.knowledge.merge_settings_repository import KnowledgeMergeSettingsRepository
from app.modules.knowledge.runtime_helpers import aggregate_method


def test_merge_settings_defaults() -> None:
    view = default_merge_settings_view("tenant_test")
    assert view.merge_rerank_enabled is False
    assert view.rerank_top_n == 20
    assert view.result_top_k == 6
    assert view.reranker_config_id is None
    assert view.policy.minimum_space_hits == 2
    assert view.policy.per_space_candidate_cap == 12


def test_merge_settings_update_requires_reranker_when_enabled() -> None:
    with pytest.raises(ValueError, match="reranker_config_id"):
        KnowledgeMergeSettingsUpdateRequest(merge_rerank_enabled=True, result_top_k=6)


def test_merge_settings_update_requires_rerank_top_n_ge_result_top_k() -> None:
    with pytest.raises(ValueError, match="rerank_top_n"):
        KnowledgeMergeSettingsUpdateRequest(
            merge_rerank_enabled=True,
            reranker_config_id="reranker_test",
            rerank_top_n=3,
            result_top_k=6,
        )


def test_disabled_merge_settings_still_require_valid_top_k_relationship() -> None:
    with pytest.raises(ValueError, match="rerank_top_n"):
        KnowledgeMergeSettingsUpdateRequest(rerank_top_n=3, result_top_k=6)


def test_disabled_merge_settings_reject_score_threshold() -> None:
    with pytest.raises(ValueError, match="min_rerank_score"):
        KnowledgeMergeSettingsUpdateRequest(min_rerank_score=0.2)


def test_merge_settings_view_maps_row() -> None:
    row = KnowledgeMergeSettings(
        tenant_id="tenant_test",
        merge_rerank_enabled=True,
        reranker_config_id="reranker_test",
        rerank_top_n=20,
        result_top_k=4,
        min_rerank_score=0.1,
    )
    view = merge_settings_view(row)
    assert view.result_top_k == 4
    assert view.merge_rerank_enabled is True


def test_aggregate_method_marks_merge_rerank() -> None:
    assert aggregate_method(True, True, False, merge_reranked=True) == "hybrid_merge_rerank"


@pytest.mark.asyncio
async def test_configured_candidates_skips_merge_when_single_space_hits() -> None:
    from app.modules.knowledge.runtime import SqlKnowledgeRuntime, _SpaceRanking
    from app.modules.knowledge.runtime_types import (
        KnowledgeRetrievalProvenance,
        KnowledgeRuntimeContext,
    )

    runtime = SqlKnowledgeRuntime(database=Mock(), settings=Mock(), cipher=Mock())
    ranking = _SpaceRanking(
        space_id="space_a",
        ranking=("chunk_1",),
        provenance=KnowledgeRetrievalProvenance("hybrid"),
        degradation_reasons=set(),
        match_sources={"chunk_1": ("lexical",)},
        vector_scores={},
        used_semantic=True,
        used_reranking=False,
    )
    runtime._configured_profiles = AsyncMock(  # type: ignore[method-assign]
        return_value=(
            (SimpleNamespace(id="space_a", embedding_config_id=None),),
            {},
            {},
        )
    )
    runtime._query_vectors = AsyncMock(return_value={})  # type: ignore[method-assign]
    runtime._rank_space = AsyncMock(return_value=ranking)  # type: ignore[method-assign]
    runtime._load_merge_settings = AsyncMock(return_value=None)  # type: ignore[method-assign]
    runtime._merge_rerank = AsyncMock()  # type: ignore[method-assign]

    selection, _embed_ms, space_count = await runtime._configured_candidates(
        KnowledgeRuntimeContext(
            tenant_id="tenant_test", agent_id="agent_test", query="crm", limit=5
        ),
        5,
    )
    assert space_count == 1
    assert selection.ranked_ids == ("chunk_1",)
    runtime._load_merge_settings.assert_not_awaited()
    runtime._merge_rerank.assert_not_awaited()


@pytest.mark.asyncio
async def test_configured_candidates_merge_reranks_when_two_spaces_hit() -> None:
    from app.modules.knowledge.runtime import SqlKnowledgeRuntime, _SpaceRanking
    from app.modules.knowledge.runtime_types import (
        KnowledgeRetrievalProvenance,
        KnowledgeRuntimeContext,
    )

    runtime = SqlKnowledgeRuntime(database=Mock(), settings=Mock(), cipher=Mock())
    rankings = (
        _SpaceRanking(
            space_id="space_a",
            ranking=("chunk_a",),
            provenance=KnowledgeRetrievalProvenance("hybrid"),
            degradation_reasons=set(),
            match_sources={},
            vector_scores={},
            used_semantic=True,
            used_reranking=False,
        ),
        _SpaceRanking(
            space_id="space_b",
            ranking=("chunk_b",),
            provenance=KnowledgeRetrievalProvenance("hybrid"),
            degradation_reasons=set(),
            match_sources={},
            vector_scores={},
            used_semantic=True,
            used_reranking=False,
        ),
    )

    merge = KnowledgeMergeSettings(
        tenant_id="tenant_test",
        merge_rerank_enabled=True,
        reranker_config_id="reranker_test",
        rerank_top_n=10,
        result_top_k=1,
        min_rerank_score=None,
    )
    runtime._configured_profiles = AsyncMock(  # type: ignore[method-assign]
        return_value=(
            (
                SimpleNamespace(id="space_a", embedding_config_id=None),
                SimpleNamespace(id="space_b", embedding_config_id=None),
            ),
            {},
            {},
        )
    )
    runtime._query_vectors = AsyncMock(return_value={})  # type: ignore[method-assign]
    runtime._rank_space = AsyncMock(side_effect=rankings)  # type: ignore[method-assign]
    runtime._load_merge_settings = AsyncMock(return_value=merge)  # type: ignore[method-assign]
    runtime._merge_rerank = AsyncMock(return_value=(("chunk_b",), None))  # type: ignore[method-assign]

    selection, _embed_ms, space_count = await runtime._configured_candidates(
        KnowledgeRuntimeContext(
            tenant_id="tenant_test", agent_id="agent_test", query="crm", limit=5
        ),
        5,
    )
    assert space_count == 2
    assert selection.ranked_ids == ("chunk_b",)
    assert selection.retrieval_method == "hybrid_merge_rerank"
    assert selection.result_limit == 1
    runtime._merge_rerank.assert_awaited_once()
    merge_call = runtime._merge_rerank.await_args
    assert merge_call is not None
    assert merge_call.args[3] == 1  # final_limit = min(5, 1)


@pytest.mark.asyncio
async def test_merge_rerank_failure_keeps_configured_result_limit() -> None:
    from app.modules.knowledge.runtime import SqlKnowledgeRuntime, _SpaceRanking
    from app.modules.knowledge.runtime_types import (
        KnowledgeRetrievalProvenance,
        KnowledgeRuntimeContext,
    )

    runtime = SqlKnowledgeRuntime(database=Mock(), settings=Mock(), cipher=Mock())
    rankings = tuple(
        _SpaceRanking(
            space_id=f"space_{space_index}",
            ranking=tuple(f"chunk_{space_index}_{index}" for index in range(20)),
            provenance=KnowledgeRetrievalProvenance("hybrid"),
            degradation_reasons=set(),
            match_sources={},
            vector_scores={},
            used_semantic=True,
            used_reranking=False,
        )
        for space_index in range(2)
    )

    merge = KnowledgeMergeSettings(
        tenant_id="tenant_test",
        merge_rerank_enabled=True,
        reranker_config_id="reranker_test",
        rerank_top_n=20,
        result_top_k=2,
        min_rerank_score=None,
    )
    runtime._configured_profiles = AsyncMock(  # type: ignore[method-assign]
        return_value=(
            (
                SimpleNamespace(id="space_0", embedding_config_id=None),
                SimpleNamespace(id="space_1", embedding_config_id=None),
            ),
            {},
            {},
        )
    )
    runtime._query_vectors = AsyncMock(return_value={})  # type: ignore[method-assign]
    runtime._rank_space = AsyncMock(side_effect=rankings)  # type: ignore[method-assign]
    runtime._load_merge_settings = AsyncMock(return_value=merge)  # type: ignore[method-assign]

    async def unavailable_merge(
        _context: KnowledgeRuntimeContext,
        _settings: KnowledgeMergeSettings,
        ranking: tuple[str, ...],
        final_limit: int,
    ) -> tuple[tuple[str, ...], str]:
        assert all(
            not item.endswith(tuple(str(index) for index in range(12, 20))) for item in ranking
        )
        return ranking[:final_limit], "merge_reranker_service_unavailable"

    runtime._merge_rerank = AsyncMock(side_effect=unavailable_merge)  # type: ignore[method-assign]

    selection, _embed_ms, _space_count = await runtime._configured_candidates(
        KnowledgeRuntimeContext(
            tenant_id="tenant_test", agent_id="agent_test", query="crm", limit=5
        ),
        5,
    )

    assert len(selection.ranked_ids) == 2
    assert selection.result_limit == 2
    assert selection.degradation_reasons == ("merge_reranker_service_unavailable",)


@pytest.mark.asyncio
async def test_merge_runtime_applies_score_threshold_and_final_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.knowledge import merge_runtime as merge_runtime_module
    from app.modules.knowledge.merge_runtime import KnowledgeMergeRuntime
    from app.modules.knowledge.runtime_types import KnowledgeRuntimeContext

    rows = [
        (
            SimpleNamespace(id="chunk_low", content="Low relevance"),
            SimpleNamespace(),
            SimpleNamespace(),
        ),
        (
            SimpleNamespace(id="chunk_high", content="High relevance"),
            SimpleNamespace(),
            SimpleNamespace(),
        ),
    ]
    merge_runtime = KnowledgeMergeRuntime(Mock(), Mock(), Mock())
    merge_runtime._active_reranker = AsyncMock(  # type: ignore[method-assign]
        return_value=SimpleNamespace(id="reranker_test")
    )
    merge_runtime._authorized_evidence = AsyncMock(return_value=rows)  # type: ignore[method-assign]
    configured = SimpleNamespace(
        rerank=AsyncMock(
            return_value=(
                SimpleNamespace(index=0, score=0.2),
                SimpleNamespace(index=1, score=0.9),
            )
        )
    )
    monkeypatch.setattr(merge_runtime_module, "ConfiguredReranker", Mock(return_value=configured))
    settings = KnowledgeMergeSettings(
        tenant_id="tenant_test",
        merge_rerank_enabled=True,
        reranker_config_id="reranker_test",
        rerank_top_n=2,
        result_top_k=1,
        min_rerank_score=0.5,
    )

    ranked, reason = await merge_runtime.rerank(
        KnowledgeRuntimeContext(
            tenant_id="tenant_test", agent_id="agent_test", query="crm", limit=5
        ),
        settings,
        ("chunk_low", "chunk_high"),
        1,
    )

    assert ranked == ("chunk_high",)
    assert reason is None


@pytest.mark.asyncio
async def test_merge_runtime_falls_back_when_provider_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.knowledge import merge_runtime as merge_runtime_module
    from app.modules.knowledge.merge_runtime import KnowledgeMergeRuntime
    from app.modules.knowledge.runtime_types import KnowledgeRuntimeContext

    rows = [
        (SimpleNamespace(id="chunk_a", content="A"), SimpleNamespace(), SimpleNamespace()),
        (SimpleNamespace(id="chunk_b", content="B"), SimpleNamespace(), SimpleNamespace()),
    ]
    merge_runtime = KnowledgeMergeRuntime(Mock(), Mock(), Mock())
    merge_runtime._active_reranker = AsyncMock(  # type: ignore[method-assign]
        return_value=SimpleNamespace(id="reranker_test")
    )
    merge_runtime._authorized_evidence = AsyncMock(return_value=rows)  # type: ignore[method-assign]
    configured = SimpleNamespace(rerank=AsyncMock(side_effect=RuntimeError("unavailable")))
    monkeypatch.setattr(merge_runtime_module, "ConfiguredReranker", Mock(return_value=configured))
    settings = KnowledgeMergeSettings(
        tenant_id="tenant_test",
        merge_rerank_enabled=True,
        reranker_config_id="reranker_test",
        rerank_top_n=2,
        result_top_k=1,
        min_rerank_score=None,
    )

    ranked, reason = await merge_runtime.rerank(
        KnowledgeRuntimeContext(
            tenant_id="tenant_test", agent_id="agent_test", query="crm", limit=5
        ),
        settings,
        ("chunk_a", "chunk_b"),
        1,
    )

    assert ranked == ("chunk_a",)
    assert reason == "merge_reranker_service_unavailable"


@pytest.mark.asyncio
async def test_retrieve_caps_expanded_evidence_to_merge_result_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.knowledge import runtime as runtime_module
    from app.modules.knowledge.runtime import SqlKnowledgeRuntime
    from app.modules.knowledge.runtime_types import (
        KnowledgeCandidateSelection,
        KnowledgeRuntimeContext,
    )

    row = (
        SimpleNamespace(
            id="chunk_test",
            content="CRM instructions",
            citation_anchor="slide-1",
            space_id="space_test",
        ),
        SimpleNamespace(id="document_test", title="CRM"),
        SimpleNamespace(id="version_test"),
    )
    selection = KnowledgeCandidateSelection(
        ranked_ids=("chunk_test",),
        scores={"chunk_test": 1.0},
        retrieval_method="hybrid_merge_rerank",
        provenance_by_space={},
        result_limit=1,
    )
    runtime = SqlKnowledgeRuntime(database=Mock(), settings=Mock(), cipher=Mock())
    runtime._configured_candidates = AsyncMock(  # type: ignore[method-assign]
        return_value=(selection, 0, 2)
    )
    runtime._authorized_evidence = AsyncMock(return_value=[row])  # type: ignore[method-assign]
    expand = AsyncMock(return_value=([row], {}))
    monkeypatch.setattr(runtime_module, "expand_evidence_bundle", expand)

    result = await runtime.retrieve(
        KnowledgeRuntimeContext(
            tenant_id="tenant_test", agent_id="agent_test", query="crm", limit=5
        )
    )

    assert result.citation_ids == ("chunk_test",)
    expand_call = expand.await_args
    assert expand_call is not None
    assert expand_call.kwargs["max_units"] == 1


def _principal(tenant_id: str, *permissions: str) -> PrincipalContext:
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


@pytest.mark.asyncio
async def test_merge_settings_get_hides_cross_tenant_resource() -> None:
    from app.modules.knowledge.merge_settings import KnowledgeMergeSettingsService

    service = KnowledgeMergeSettingsService(
        cast(AsyncSession, SimpleNamespace()),
        cast(DatabaseManager, SimpleNamespace(set_tenant=AsyncMock())),
    )

    with pytest.raises(AppError) as error:
        await service.get(_principal("tenant_a", "knowledge.spaces.read"), "tenant_b")

    assert error.value.status_code == 404
    assert error.value.code == "RESOURCE_NOT_FOUND"


@pytest.mark.asyncio
async def test_merge_settings_update_requires_manage_permission() -> None:
    from app.modules.knowledge.merge_settings import KnowledgeMergeSettingsService

    service = KnowledgeMergeSettingsService(
        cast(AsyncSession, SimpleNamespace()),
        cast(DatabaseManager, SimpleNamespace(set_tenant=AsyncMock())),
    )

    with pytest.raises(AppError) as error:
        await service.update(
            _principal("tenant_test", "knowledge.spaces.read"),
            "tenant_test",
            KnowledgeMergeSettingsUpdateRequest(),
        )

    assert error.value.status_code == 403
    assert error.value.code == "FORBIDDEN"


@pytest.mark.asyncio
async def test_merge_settings_repository_requires_matching_tenant_for_reranker() -> None:
    session = cast(AsyncSession, SimpleNamespace(scalar=AsyncMock(return_value=None)))

    result = await KnowledgeMergeSettingsRepository(session).active_reranker(
        "tenant_test", "reranker_other"
    )

    assert result is None
    scalar = cast(AsyncMock, session.scalar)
    scalar_call = scalar.await_args
    assert scalar_call is not None
    statement = scalar_call.args[0]
    assert "reranker_configs.tenant_id" in str(statement)
