from __future__ import annotations

import logging

from app.core.config import AppConfig
from app.modules.memory.embedding import OpenAiCompatibleEmbeddingClient
from app.modules.memory.retrieval import (
    MemorySearchContext,
    SemanticMemoryCandidates,
    SemanticMemorySearchPort,
)
from app.modules.memory.vector_store import (
    MemoryVectorSearchContext,
    MemoryVectorStore,
    MilvusMemoryVectorStore,
)

logger = logging.getLogger(__name__)


class VectorMemorySearch(SemanticMemorySearchPort):
    def __init__(
        self, embeddings: OpenAiCompatibleEmbeddingClient, vectors: MemoryVectorStore
    ) -> None:
        self._embeddings = embeddings
        self._vectors = vectors

    async def search(
        self, context: MemorySearchContext, query: str, limit: int
    ) -> SemanticMemoryCandidates:
        try:
            vectors = await self._embeddings.embed((query,))
            if not vectors:
                return SemanticMemoryCandidates((), True)
            ids = await self._vectors.search(
                vectors[0],
                MemoryVectorSearchContext(
                    tenant_id=context.tenant_id,
                    agent_id=context.agent_id,
                    actor_id=context.actor_id or "",
                    conversation_id=context.conversation_id,
                ),
                limit,
            )
            return SemanticMemoryCandidates(ids, True)
        except Exception:
            logger.exception(
                "Runtime vector memory search failed", extra={"tenant_id": context.tenant_id}
            )
            return SemanticMemoryCandidates((), False)


class UnavailableMemorySearch(SemanticMemorySearchPort):
    async def search(
        self, context: MemorySearchContext, query: str, limit: int
    ) -> SemanticMemoryCandidates:
        del context, query, limit
        return SemanticMemoryCandidates((), False)


def build_memory_semantic_search(settings: AppConfig) -> SemanticMemorySearchPort | None:
    if not settings.memory.vector.enabled:
        return None
    try:
        return VectorMemorySearch(
            OpenAiCompatibleEmbeddingClient(settings), MilvusMemoryVectorStore(settings)
        )
    except ValueError:
        logger.warning("Memory semantic search is unavailable during configuration")
        return UnavailableMemorySearch()
