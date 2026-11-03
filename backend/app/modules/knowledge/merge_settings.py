from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.errors import AppError
from app.infrastructure.db.session import DatabaseManager
from app.modules.audit.service import append_audit
from app.modules.iam.schemas import PrincipalContext
from app.modules.knowledge.access import KnowledgeAccessPolicy
from app.modules.knowledge.merge_models import KnowledgeMergeSettings
from app.modules.knowledge.merge_policy import (
    MERGE_RERANK_TOP_N_DEFAULT,
    MERGE_RESULT_TOP_K_DEFAULT,
)
from app.modules.knowledge.merge_schemas import (
    KnowledgeMergePolicyView,
    KnowledgeMergeSettingsUpdateRequest,
    KnowledgeMergeSettingsView,
)
from app.modules.knowledge.merge_settings_repository import KnowledgeMergeSettingsRepository


def default_merge_settings_view(tenant_id: str) -> KnowledgeMergeSettingsView:
    return KnowledgeMergeSettingsView(
        tenant_id=tenant_id,
        merge_rerank_enabled=False,
        reranker_config_id=None,
        rerank_top_n=MERGE_RERANK_TOP_N_DEFAULT,
        result_top_k=MERGE_RESULT_TOP_K_DEFAULT,
        min_rerank_score=None,
        policy=KnowledgeMergePolicyView(),
        updated_at=None,
    )


def merge_settings_view(row: KnowledgeMergeSettings) -> KnowledgeMergeSettingsView:
    return KnowledgeMergeSettingsView(
        tenant_id=row.tenant_id,
        merge_rerank_enabled=row.merge_rerank_enabled,
        reranker_config_id=row.reranker_config_id,
        rerank_top_n=row.rerank_top_n,
        result_top_k=row.result_top_k,
        min_rerank_score=row.min_rerank_score,
        policy=KnowledgeMergePolicyView(),
        updated_at=row.updated_at,
    )


class KnowledgeMergeSettingsService:
    def __init__(self, session: AsyncSession, database: DatabaseManager) -> None:
        self.session = session
        self.access_policy = KnowledgeAccessPolicy(session, database)
        self.repository = KnowledgeMergeSettingsRepository(session)

    async def get(self, principal: PrincipalContext, tenant_id: str) -> KnowledgeMergeSettingsView:
        await self.access_policy.enter(
            principal,
            tenant_id,
            "knowledge.spaces.read",
            not_found_message="Knowledge space not found",
        )
        row = await self.repository.get(tenant_id)
        if row is None:
            return default_merge_settings_view(tenant_id)
        return merge_settings_view(row)

    async def update(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        payload: KnowledgeMergeSettingsUpdateRequest,
    ) -> KnowledgeMergeSettingsView:
        await self.access_policy.enter(
            principal,
            tenant_id,
            "knowledge.spaces.manage",
            not_found_message="Knowledge space not found",
        )
        if payload.merge_rerank_enabled:
            await self._require_active_reranker(tenant_id, payload.reranker_config_id)
        row = await self.repository.get(tenant_id)
        if row is None:
            row = KnowledgeMergeSettings(tenant_id=tenant_id)
            self.session.add(row)
        row.merge_rerank_enabled = payload.merge_rerank_enabled
        row.reranker_config_id = (
            payload.reranker_config_id if payload.merge_rerank_enabled else None
        )
        row.rerank_top_n = payload.rerank_top_n
        row.result_top_k = payload.result_top_k
        row.min_rerank_score = payload.min_rerank_score if payload.merge_rerank_enabled else None
        await self.session.flush()
        append_audit(
            self.session,
            principal,
            "knowledge.merge_settings.update",
            "knowledge_merge_settings",
            tenant_id,
            {
                "merge_rerank_enabled": row.merge_rerank_enabled,
                "reranker_config_id": row.reranker_config_id,
                "rerank_top_n": row.rerank_top_n,
                "result_top_k": row.result_top_k,
                "min_rerank_score": row.min_rerank_score,
            },
            tenant_id=tenant_id,
        )
        return merge_settings_view(row)

    async def _require_active_reranker(
        self, tenant_id: str, reranker_config_id: str | None
    ) -> None:
        if reranker_config_id is None:
            raise AppError(
                "RERANKER_CONFIG_NOT_FOUND",
                "Reranker config is unavailable",
                status.HTTP_422_UNPROCESSABLE_CONTENT,
            )
        reranker = await self.repository.active_reranker(tenant_id, reranker_config_id)
        if reranker is None:
            raise AppError(
                "RERANKER_CONFIG_NOT_FOUND",
                "Reranker config is unavailable",
                status.HTTP_422_UNPROCESSABLE_CONTENT,
            )
