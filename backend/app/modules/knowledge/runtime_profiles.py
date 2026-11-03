from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.embedding_configs.models import EmbeddingConfig
from app.modules.knowledge.models import KnowledgeSpace
from app.modules.reranker_configs.models import RerankerConfig


async def load_retrieval_profiles(
    session: AsyncSession,
    tenant_id: str,
    spaces: tuple[KnowledgeSpace, ...],
) -> tuple[dict[str, EmbeddingConfig], dict[str, RerankerConfig]]:
    embedding_ids = tuple(
        space.embedding_config_id for space in spaces if space.embedding_config_id is not None
    )
    reranker_ids = tuple(
        space.reranker_config_id for space in spaces if space.reranker_config_id is not None
    )
    embeddings = (
        await session.scalars(
            select(EmbeddingConfig).where(
                EmbeddingConfig.tenant_id == tenant_id,
                EmbeddingConfig.id.in_(embedding_ids),
            )
        )
        if embedding_ids
        else ()
    )
    rerankers = (
        await session.scalars(
            select(RerankerConfig).where(
                RerankerConfig.tenant_id == tenant_id,
                RerankerConfig.id.in_(reranker_ids),
                RerankerConfig.status == "active",
            )
        )
        if reranker_ids
        else ()
    )
    return {item.id: item for item in embeddings}, {item.id: item for item in rerankers}
