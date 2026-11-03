from __future__ import annotations

from typing import Protocol

from app.modules.knowledge.embedding import KnowledgeEmbeddingPort
from app.modules.knowledge.vector_store import KnowledgeVectorSearchScope, KnowledgeVectorStore


class KnowledgeSemanticSearchPort(Protocol):
    async def search(
        self,
        tenant_id: str,
        space_ids: tuple[str, ...],
        query: str,
        limit: int,
    ) -> tuple[str, ...]: ...


class KnowledgeSemanticSearch:
    def __init__(self, embeddings: KnowledgeEmbeddingPort, vectors: KnowledgeVectorStore) -> None:
        self._embeddings = embeddings
        self._vectors = vectors

    async def search(
        self,
        tenant_id: str,
        space_ids: tuple[str, ...],
        query: str,
        limit: int,
    ) -> tuple[str, ...]:
        if not space_ids or not query.strip():
            return ()
        embeddings = await self._embeddings.embed((query.strip(),))
        if len(embeddings) != 1:
            raise ValueError("Knowledge embedding service returned an incomplete query vector")
        return await self._vectors.search(
            embeddings[0],
            KnowledgeVectorSearchScope(tenant_id=tenant_id, space_ids=space_ids),
            limit,
        )
