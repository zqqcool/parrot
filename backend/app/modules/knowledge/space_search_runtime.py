from __future__ import annotations

from app.modules.embedding_configs.models import EmbeddingConfig
from app.modules.knowledge.models import KnowledgeSpace
from app.modules.knowledge.runtime import SqlKnowledgeRuntime
from app.modules.knowledge.runtime_profiles import load_retrieval_profiles
from app.modules.knowledge.runtime_repository import (
    KnowledgeEvidenceRow,
    KnowledgeRuntimeRepository,
)
from app.modules.knowledge.runtime_types import KnowledgeEvidenceBundle, KnowledgeRuntimeContext
from app.modules.reranker_configs.models import RerankerConfig


class KnowledgeSpaceSearchRuntime(SqlKnowledgeRuntime):
    """Run the Agent retrieval algorithm against one service-authorized knowledge space."""

    async def search(
        self, tenant_id: str, space_id: str, query: str, candidate_top_k: int
    ) -> KnowledgeEvidenceBundle:
        return await self.retrieve(
            KnowledgeRuntimeContext(
                tenant_id=tenant_id,
                agent_id=space_id,
                query=query,
                limit=candidate_top_k,
            )
        )

    async def _configured_profiles(
        self, context: KnowledgeRuntimeContext
    ) -> tuple[tuple[KnowledgeSpace, ...], dict[str, EmbeddingConfig], dict[str, RerankerConfig]]:
        async with self._database.session() as session:
            await self._database.set_tenant(session, context.tenant_id)
            space = await KnowledgeRuntimeRepository(session).active_space(
                context.tenant_id, context.agent_id
            )
            if space is None:
                return (), {}, {}
            embeddings, rerankers = await load_retrieval_profiles(
                session, context.tenant_id, (space,)
            )
            return (space,), embeddings, rerankers

    async def _lexical_candidates_in_space(
        self, context: KnowledgeRuntimeContext, space_id: str, limit: int
    ) -> tuple[str, ...]:
        async with self._database.session() as session:
            await self._database.set_tenant(session, context.tenant_id)
            evidence = await KnowledgeRuntimeRepository(session).lexical_search_for_space(
                context.tenant_id, space_id, context.query.strip(), limit
            )
            return tuple(item[0].id for item in evidence)

    async def _authorized_evidence(
        self, context: KnowledgeRuntimeContext, chunk_ids: tuple[str, ...]
    ) -> list[KnowledgeEvidenceRow]:
        async with self._database.session() as session:
            await self._database.set_tenant(session, context.tenant_id)
            return await KnowledgeRuntimeRepository(session).published_candidates_for_space(
                context.tenant_id, context.agent_id, chunk_ids
            )

    def _space_scoped_expand(self) -> bool:
        return True
