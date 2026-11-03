from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal, Protocol

from app.core.agent_runtime import DEFAULT_CAPABILITY_RELEVANCE_THRESHOLD
from app.core.config import AppConfig
from app.modules.capability_index.ranking import CapabilitySearchDocument, bm25_rank, rrf_rank
from app.modules.capability_index.vector_store import (
    CapabilityVectorStore,
    MilvusCapabilityVectorStore,
)
from app.modules.knowledge.embedding import (
    KnowledgeEmbeddingError,
    KnowledgeEmbeddingPort,
    OpenAiCompatibleKnowledgeEmbedding,
)

logger = logging.getLogger(__name__)

CapabilityRetrievalMethod = Literal["bm25", "hybrid", "bm25_fallback"]


@dataclass(frozen=True)
class CapabilitySearchOutcome:
    source_ids: tuple[str, ...]
    retrieval_method: CapabilityRetrievalMethod
    relevance_scores: tuple[tuple[str, float], ...] = ()

    def relevance_score_for(self, source_id: str) -> float | None:
        return next(
            (score for item_id, score in self.relevance_scores if item_id == source_id), None
        )


class CapabilitySearchRanker(Protocol):
    async def rank(
        self,
        tenant_id: str,
        query: str,
        documents: tuple[CapabilitySearchDocument, ...],
        *,
        minimum_relevance_score: float = DEFAULT_CAPABILITY_RELEVANCE_THRESHOLD,
    ) -> tuple[str, ...]: ...


class CapabilitySearchEvaluator(Protocol):
    async def evaluate(
        self,
        tenant_id: str,
        query: str,
        documents: tuple[CapabilitySearchDocument, ...],
        *,
        minimum_relevance_score: float = DEFAULT_CAPABILITY_RELEVANCE_THRESHOLD,
    ) -> CapabilitySearchOutcome: ...


class SystemCapabilityHybridSearch:
    """BM25 is always available; system embedding/Milvus augments it when healthy."""

    def __init__(
        self,
        settings: AppConfig,
        *,
        embeddings: KnowledgeEmbeddingPort | None = None,
        vectors: CapabilityVectorStore | None = None,
    ) -> None:
        self._embeddings = embeddings or OpenAiCompatibleKnowledgeEmbedding(
            settings, section=settings.capability_index.embedding
        )
        try:
            self._vectors = vectors or MilvusCapabilityVectorStore(settings)
        except ValueError:
            self._vectors = None

    async def rank(
        self,
        tenant_id: str,
        query: str,
        documents: tuple[CapabilitySearchDocument, ...],
        *,
        minimum_relevance_score: float = DEFAULT_CAPABILITY_RELEVANCE_THRESHOLD,
    ) -> tuple[str, ...]:
        return (
            await self.evaluate(
                tenant_id,
                query,
                documents,
                minimum_relevance_score=minimum_relevance_score,
            )
        ).source_ids

    async def evaluate(
        self,
        tenant_id: str,
        query: str,
        documents: tuple[CapabilitySearchDocument, ...],
        *,
        minimum_relevance_score: float = DEFAULT_CAPABILITY_RELEVANCE_THRESHOLD,
    ) -> CapabilitySearchOutcome:
        lexical = bm25_rank(query, documents)
        if not documents or not query.strip() or self._vectors is None:
            return CapabilitySearchOutcome(rrf_rank(lexical, limit=None), "bm25")
        try:
            embedded = await self._embeddings.embed((query,))
            if not embedded:
                raise ValueError("Capability embedding service returned no query vector")
            hits = await self._vectors.search(
                embedded[0],
                tenant_id,
                tuple(item.source_id for item in documents),
                len(documents),
            )
            if not hits:
                raise ValueError("Capability vector index returned no eligible source vectors")
            semantic = tuple(
                item.source_id for item in hits if item.score >= minimum_relevance_score
            )
            eligible = set(semantic)
            lexical = tuple(source_id for source_id in lexical if source_id in eligible)
        except (KnowledgeEmbeddingError, ValueError, OSError):
            logger.warning("Capability semantic retrieval unavailable; using BM25", exc_info=True)
            return CapabilitySearchOutcome(rrf_rank(lexical, limit=None), "bm25_fallback")
        return CapabilitySearchOutcome(
            rrf_rank(lexical, semantic, limit=None),
            "hybrid",
            tuple((item.source_id, item.score) for item in hits),
        )
