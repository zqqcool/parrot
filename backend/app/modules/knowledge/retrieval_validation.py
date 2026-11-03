from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.config import AppConfig, knowledge_vector_runtime_issue
from app.core.errors import AppError
from app.modules.embedding_configs.models import EmbeddingConfig
from app.modules.knowledge.schemas import (
    KnowledgeSpaceCreateRequest,
    KnowledgeSpaceRetrievalUpdateRequest,
)


async def validate_retrieval_configs(
    session: AsyncSession,
    settings: AppConfig | None,
    tenant_id: str,
    payload: KnowledgeSpaceCreateRequest | KnowledgeSpaceRetrievalUpdateRequest,
    *,
    allow_disabled_embedding: bool = False,
) -> EmbeddingConfig | None:
    if payload.embedding_config_id is None:
        return None
    if settings is None or knowledge_vector_runtime_issue(settings):
        raise AppError(
            "KNOWLEDGE_VECTOR_RUNTIME_UNAVAILABLE",
            "Knowledge vector runtime is unavailable",
            status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    statement = select(EmbeddingConfig).where(
        EmbeddingConfig.tenant_id == tenant_id,
        EmbeddingConfig.id == payload.embedding_config_id,
    )
    if not allow_disabled_embedding:
        statement = statement.where(EmbeddingConfig.status == "active")
    embedding = await session.scalar(statement)
    if embedding is None:
        raise AppError(
            "EMBEDDING_CONFIG_NOT_FOUND",
            "Embedding config is unavailable",
            status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    reranker_config_id = getattr(payload, "reranker_config_id", None)
    if reranker_config_id is None:
        return embedding
    from app.modules.reranker_configs.models import RerankerConfig

    reranker = await session.scalar(
        select(RerankerConfig.id).where(
            RerankerConfig.tenant_id == tenant_id,
            RerankerConfig.id == reranker_config_id,
            RerankerConfig.status == "active",
        )
    )
    if reranker is None:
        raise AppError(
            "RERANKER_CONFIG_NOT_FOUND",
            "Reranker config is unavailable",
            status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    return embedding
