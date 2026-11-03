from __future__ import annotations

import logging

from app.core.config import AppConfig
from app.infrastructure.credential_cipher import CredentialCipher
from app.infrastructure.db.session import DatabaseManager
from app.modules.knowledge import runtime_helpers
from app.modules.knowledge.merge_models import KnowledgeMergeSettings
from app.modules.knowledge.merge_settings_repository import KnowledgeMergeSettingsRepository
from app.modules.knowledge.retrieval_clients import ConfiguredReranker
from app.modules.knowledge.runtime_repository import (
    KnowledgeEvidenceRow,
    KnowledgeRuntimeRepository,
)
from app.modules.knowledge.runtime_types import KnowledgeRuntimeContext
from app.modules.reranker_configs.models import RerankerConfig

logger = logging.getLogger(__name__)


class KnowledgeMergeRuntime:
    """Tenant-scoped configuration and execution for cross-space reranking."""

    def __init__(
        self,
        database: DatabaseManager,
        settings: AppConfig,
        cipher: CredentialCipher,
    ) -> None:
        self._database = database
        self._settings = settings
        self._cipher = cipher

    async def load_settings(self, tenant_id: str) -> KnowledgeMergeSettings | None:
        async with self._database.session() as session:
            await self._database.set_tenant(session, tenant_id)
            return await KnowledgeMergeSettingsRepository(session).get(tenant_id)

    async def rerank(
        self,
        context: KnowledgeRuntimeContext,
        settings: KnowledgeMergeSettings,
        ranking: tuple[str, ...],
        final_limit: int,
    ) -> tuple[tuple[str, ...], str | None]:
        if not ranking:
            return (), None
        candidates = ranking[: settings.rerank_top_n]
        reranker = await self._active_reranker(context.tenant_id, settings.reranker_config_id)
        if reranker is None:
            return ranking[:final_limit], "merge_reranker_config_unavailable"
        evidence = await self._authorized_evidence(context, candidates)
        if not evidence:
            return (), None
        try:
            results = await ConfiguredReranker(self._settings, self._cipher, reranker).rerank(
                context.query.strip(),
                tuple(
                    runtime_helpers.bounded(chunk.content, 2_000)
                    for chunk, _document, _version in evidence
                ),
                min(settings.rerank_top_n, len(evidence)),
            )
        except Exception:
            logger.exception(
                "Knowledge merge reranking failed; using RRF candidates",
                extra={"tenant_id": context.tenant_id, "agent_id": context.agent_id},
            )
            return ranking[:final_limit], "merge_reranker_service_unavailable"
        ranked = tuple(
            evidence[item.index][0].id
            for item in results
            if settings.min_rerank_score is None or item.score >= settings.min_rerank_score
        )
        return ranked[:final_limit], None

    async def _active_reranker(
        self, tenant_id: str, config_id: str | None
    ) -> RerankerConfig | None:
        if config_id is None:
            return None
        async with self._database.session() as session:
            await self._database.set_tenant(session, tenant_id)
            return await KnowledgeMergeSettingsRepository(session).active_reranker(
                tenant_id, config_id
            )

    async def _authorized_evidence(
        self, context: KnowledgeRuntimeContext, chunk_ids: tuple[str, ...]
    ) -> list[KnowledgeEvidenceRow]:
        async with self._database.session() as session:
            await self._database.set_tenant(session, context.tenant_id)
            return await KnowledgeRuntimeRepository(session).authorized_candidates(
                context.tenant_id, context.agent_id, chunk_ids
            )
