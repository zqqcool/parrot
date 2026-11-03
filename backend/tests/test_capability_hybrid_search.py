from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest

from app.core.agent_runtime import RuntimeSkillProfile
from app.core.config import AppConfig
from app.modules.agent_runtime.capabilities import CapabilitySession
from app.modules.agent_runtime.skill_executor import SkillExecutionContext
from app.modules.capability_index.hybrid_search import (
    CapabilitySearchRanker,
    SystemCapabilityHybridSearch,
)
from app.modules.capability_index.ranking import CapabilitySearchDocument
from app.modules.capability_index.vector_store import CapabilityVectorHit, CapabilityVectorStore
from app.modules.knowledge.embedding import KnowledgeEmbeddingPort


@pytest.mark.asyncio
async def test_capability_find_uses_ranker_limits_results_and_indexes_skill_md() -> None:
    skills = tuple(
        RuntimeSkillProfile(
            id=f"skill_{index}",
            name=f"Skill {index}",
            description=f"description {index}",
            instructions=f"SKILL instructions {index}",
            manifest={},
            version=1,
        )
        for index in range(3)
    )
    ranker = SimpleNamespace(rank=AsyncMock(return_value=("skill_2", "skill_1", "skill_0")))
    session = CapabilitySession(
        skills,
        minimum_relevance_score=0.45,
        search_ranker=cast(CapabilitySearchRanker, ranker),
        execution_context=SkillExecutionContext(
            tenant_id="tenant_test",
            interaction_id="interaction_test",
            actor_type="user",
            actor_id="user_test",
            request_id="request_test",
        ),
    )

    result = await session.search("find", "help", None)
    loaded = await session.search("load", None, "skill_2")

    assert [item["id"] for item in cast(list[dict[str, str]], result["capabilities"])] == [
        "skill_2",
        "skill_1",
    ]
    documents = ranker.rank.await_args.args[2]
    assert ranker.rank.await_args.kwargs == {"minimum_relevance_score": 0.45}
    assert "name: Skill 2" in documents[2].text
    assert "description: description 2" in documents[2].text
    assert "SKILL.md:\nSKILL instructions 2" in documents[2].text
    assert loaded["instructions"] == "SKILL instructions 2"


@pytest.mark.asyncio
async def test_capability_find_and_load_ranks_and_loads_top_skill() -> None:
    skills = tuple(
        RuntimeSkillProfile(
            id=f"skill_{index}",
            name=f"Skill {index}",
            description=f"description {index}",
            instructions=f"SKILL instructions {index}",
            manifest={},
            version=1,
        )
        for index in range(3)
    )
    ranker = SimpleNamespace(rank=AsyncMock(return_value=("skill_2", "skill_1", "skill_0")))
    session = CapabilitySession(
        skills,
        minimum_relevance_score=0.45,
        search_ranker=cast(CapabilitySearchRanker, ranker),
        execution_context=SkillExecutionContext(
            tenant_id="tenant_test",
            interaction_id="interaction_test",
            actor_type="user",
            actor_id="user_test",
            request_id="request_test",
        ),
    )

    result = await session.search("find_and_load", "help", None)

    assert [item["id"] for item in cast(list[dict[str, str]], result["capabilities"])] == [
        "skill_2",
        "skill_1",
    ]
    assert result["capability"]["id"] == "skill_2"
    assert result["instructions"] == "SKILL instructions 2"
    assert "skill_2" in session.loaded_skill_ids


@pytest.mark.asyncio
async def test_capability_find_and_load_with_empty_query_lists_without_loading() -> None:
    skills = (
        RuntimeSkillProfile(
            id="skill_a",
            name="Skill A",
            description="alpha",
            instructions="instructions a",
            manifest={},
            version=1,
        ),
    )
    session = CapabilitySession(skills)

    result = await session.search("find_and_load", "", None)

    assert [item["id"] for item in cast(list[dict[str, str]], result["capabilities"])] == [
        "skill_a"
    ]
    assert "instructions" not in result
    assert session.loaded_skill_ids == set()


@pytest.mark.asyncio
async def test_hybrid_search_falls_back_to_bm25_when_system_vector_is_unavailable() -> None:
    embeddings = SimpleNamespace(embed=AsyncMock(return_value=((0.1, 0.2),)))
    vectors = SimpleNamespace(search=AsyncMock(side_effect=OSError("Milvus unavailable")))
    search = SystemCapabilityHybridSearch(
        cast(AppConfig, SimpleNamespace()),
        embeddings=cast(KnowledgeEmbeddingPort, embeddings),
        vectors=cast(CapabilityVectorStore, vectors),
    )

    outcome = await search.evaluate(
        "tenant_test",
        "calendar",
        (
            CapabilitySearchDocument("calendar", "calendar schedule management"),
            CapabilitySearchDocument("other", "unrelated text"),
        ),
    )

    assert outcome.source_ids == ("calendar",)
    assert outcome.retrieval_method == "bm25_fallback"


@pytest.mark.asyncio
async def test_hybrid_search_combines_system_vector_candidates() -> None:
    embeddings = SimpleNamespace(embed=AsyncMock(return_value=((0.1, 0.2),)))
    vectors = SimpleNamespace(
        search=AsyncMock(
            return_value=(
                CapabilityVectorHit("semantic", 0.9),
                CapabilityVectorHit("lexical", 0.8),
            )
        )
    )
    search = SystemCapabilityHybridSearch(
        cast(AppConfig, SimpleNamespace()),
        embeddings=cast(KnowledgeEmbeddingPort, embeddings),
        vectors=cast(CapabilityVectorStore, vectors),
    )

    outcome = await search.evaluate(
        "tenant_test",
        "calendar",
        (
            CapabilitySearchDocument("lexical", "calendar schedule management"),
            CapabilitySearchDocument("semantic", "meeting assistant"),
        ),
    )

    assert outcome.source_ids == ("lexical", "semantic")
    assert outcome.retrieval_method == "hybrid"
    assert outcome.relevance_score_for("semantic") == 0.9


@pytest.mark.asyncio
async def test_hybrid_search_filters_low_score_semantic_only_candidate() -> None:
    embeddings = SimpleNamespace(embed=AsyncMock(return_value=((0.1, 0.2),)))
    vectors = SimpleNamespace(search=AsyncMock(return_value=(CapabilityVectorHit("hotel", 0.31),)))
    search = SystemCapabilityHybridSearch(
        cast(AppConfig, SimpleNamespace()),
        embeddings=cast(KnowledgeEmbeddingPort, embeddings),
        vectors=cast(CapabilityVectorStore, vectors),
    )

    outcome = await search.evaluate(
        "tenant_test",
        "苹果",
        (CapabilitySearchDocument("hotel", "hotel check-in and booking service"),),
        minimum_relevance_score=0.4,
    )

    assert outcome.source_ids == ()
    assert outcome.relevance_score_for("hotel") == 0.31
    assert outcome.retrieval_method == "hybrid"


@pytest.mark.asyncio
async def test_hybrid_search_keeps_semantic_candidate_above_threshold() -> None:
    embeddings = SimpleNamespace(embed=AsyncMock(return_value=((0.1, 0.2),)))
    vectors = SimpleNamespace(search=AsyncMock(return_value=(CapabilityVectorHit("hotel", 0.53),)))
    search = SystemCapabilityHybridSearch(
        cast(AppConfig, SimpleNamespace()),
        embeddings=cast(KnowledgeEmbeddingPort, embeddings),
        vectors=cast(CapabilityVectorStore, vectors),
    )

    outcome = await search.evaluate(
        "tenant_test",
        "我需要预约服务",
        (CapabilitySearchDocument("hotel", "hotel check-in and booking service"),),
        minimum_relevance_score=0.4,
    )

    assert outcome.source_ids == ("hotel",)
    assert outcome.relevance_score_for("hotel") == 0.53


@pytest.mark.asyncio
async def test_hybrid_search_filters_low_score_lexical_candidate_when_vectors_are_healthy() -> None:
    embeddings = SimpleNamespace(embed=AsyncMock(return_value=((0.1, 0.2),)))
    vectors = SimpleNamespace(search=AsyncMock(return_value=(CapabilityVectorHit("hotel", 0.31),)))
    search = SystemCapabilityHybridSearch(
        cast(AppConfig, SimpleNamespace()),
        embeddings=cast(KnowledgeEmbeddingPort, embeddings),
        vectors=cast(CapabilityVectorStore, vectors),
    )

    outcome = await search.evaluate(
        "tenant_test",
        "苹果",
        (CapabilitySearchDocument("hotel", "在用户确认后创建测试工单并反馈结果"),),
        minimum_relevance_score=0.4,
    )

    assert outcome.source_ids == ()
    assert outcome.relevance_score_for("hotel") == 0.31


@pytest.mark.asyncio
async def test_hybrid_search_does_not_call_embedding_without_eligible_documents() -> None:
    embeddings = SimpleNamespace(embed=AsyncMock())
    vectors = SimpleNamespace(search=AsyncMock())
    search = SystemCapabilityHybridSearch(
        cast(AppConfig, SimpleNamespace()),
        embeddings=cast(KnowledgeEmbeddingPort, embeddings),
        vectors=cast(CapabilityVectorStore, vectors),
    )

    outcome = await search.evaluate("tenant_test", "calendar", ())

    assert outcome.source_ids == ()
    assert outcome.retrieval_method == "bm25"
    embeddings.embed.assert_not_awaited()
    vectors.search.assert_not_awaited()
