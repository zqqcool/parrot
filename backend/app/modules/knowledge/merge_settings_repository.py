from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.knowledge.merge_models import KnowledgeMergeSettings
from app.modules.reranker_configs.models import RerankerConfig


class KnowledgeMergeSettingsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, tenant_id: str) -> KnowledgeMergeSettings | None:
        return await self.session.scalar(
            select(KnowledgeMergeSettings).where(KnowledgeMergeSettings.tenant_id == tenant_id)
        )

    async def active_reranker(
        self, tenant_id: str, reranker_config_id: str
    ) -> RerankerConfig | None:
        return await self.session.scalar(
            select(RerankerConfig).where(
                RerankerConfig.tenant_id == tenant_id,
                RerankerConfig.id == reranker_config_id,
                RerankerConfig.status == "active",
            )
        )

    async def reranker_in_use(self, tenant_id: str, reranker_config_id: str) -> bool:
        return (
            await self.session.scalar(
                select(KnowledgeMergeSettings.tenant_id).where(
                    KnowledgeMergeSettings.tenant_id == tenant_id,
                    KnowledgeMergeSettings.reranker_config_id == reranker_config_id,
                )
            )
        ) is not None
