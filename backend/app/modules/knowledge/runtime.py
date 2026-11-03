from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from time import perf_counter

from app.core.config import AppConfig, knowledge_vector_runtime_issue
from app.infrastructure.credential_cipher import CredentialCipher
from app.infrastructure.db.session import DatabaseManager
from app.modules.embedding_configs.models import EmbeddingConfig
from app.modules.knowledge import runtime_helpers
from app.modules.knowledge.embedding_profile import embedding_snapshot_matches
from app.modules.knowledge.evidence_assembly import expand_evidence_bundle
from app.modules.knowledge.merge_models import KnowledgeMergeSettings
from app.modules.knowledge.merge_policy import (
    MERGE_MINIMUM_SPACE_HITS,
    MERGE_PER_SPACE_CANDIDATE_CAP,
)
from app.modules.knowledge.merge_runtime import KnowledgeMergeRuntime
from app.modules.knowledge.models import KnowledgeSpace
from app.modules.knowledge.retrieval_clients import ConfiguredKnowledgeEmbedding, ConfiguredReranker
from app.modules.knowledge.runtime_profiles import load_retrieval_profiles
from app.modules.knowledge.runtime_repository import (
    KnowledgeEvidenceRow,
    KnowledgeRuntimeRepository,
)
from app.modules.knowledge.runtime_types import (
    KnowledgeCandidateSelection,
    KnowledgeEvidenceBundle,
    KnowledgeEvidenceItem,
    KnowledgeMatchSource,
    KnowledgeMediaRef,
    KnowledgeRetrievalProvenance,
    KnowledgeRuntimeContext,
    KnowledgeRuntimePort,
)
from app.modules.knowledge.semantic_search import KnowledgeSemanticSearchPort
from app.modules.knowledge.vector_store import (
    KnowledgeVectorSearchScope,
    MilvusKnowledgeVectorStore,
)
from app.modules.reranker_configs.models import RerankerConfig

logger = logging.getLogger(__name__)
reciprocal_rank_fusion = runtime_helpers.reciprocal_rank_fusion
reciprocal_rank_fusion_many = runtime_helpers.reciprocal_rank_fusion_many
_MAX_PARALLEL_SPACES = 4

__all__ = (
    "KnowledgeEvidenceBundle",
    "KnowledgeEvidenceItem",
    "KnowledgeRuntimeContext",
    "KnowledgeRuntimePort",
    "SqlKnowledgeRuntime",
    "reciprocal_rank_fusion",
    "reciprocal_rank_fusion_many",
)


@dataclass(frozen=True)
class _SpaceRanking:
    space_id: str
    ranking: tuple[str, ...]
    provenance: KnowledgeRetrievalProvenance
    degradation_reasons: set[str]
    match_sources: dict[str, tuple[KnowledgeMatchSource, ...]]
    vector_scores: dict[str, float]
    used_semantic: bool
    used_reranking: bool


class SqlKnowledgeRuntime:
    """Agent-bound retrieval with per-space tenant model configuration and authorization."""

    def __init__(
        self,
        database: DatabaseManager,
        semantic_search: KnowledgeSemanticSearchPort | None = None,
        *,
        retrieval_mode: str = "lexical",
        candidate_multiplier: int = 4,
        reciprocal_rank_constant: int = 60,
        settings: AppConfig | None = None,
        cipher: CredentialCipher | None = None,
    ) -> None:
        self._database = database
        self._semantic_search = semantic_search
        self._retrieval_mode = retrieval_mode
        self._candidate_multiplier = candidate_multiplier
        self._reciprocal_rank_constant = reciprocal_rank_constant
        self._settings = settings
        self._cipher = cipher
        self._merge_runtime = (
            KnowledgeMergeRuntime(database, settings, cipher)
            if settings is not None and cipher is not None
            else None
        )

    async def retrieve(self, context: KnowledgeRuntimeContext) -> KnowledgeEvidenceBundle:
        if not context.query.strip():
            return KnowledgeEvidenceBundle(status="not_applicable")
        started = perf_counter()
        limit = max(1, min(context.limit, 60))
        embed_duration_ms = 0
        space_count = 0
        try:
            if self._settings is not None and self._cipher is not None:
                selection, embed_duration_ms, space_count = await self._configured_candidates(
                    context, limit
                )
            else:
                selection = await self._legacy_candidates(context, limit)
            seed = await self._authorized_evidence(context, selection.ranked_ids)
            evidence, media_refs = await expand_evidence_bundle(
                self._database,
                tenant_id=context.tenant_id,
                agent_id=context.agent_id,
                seed=seed,
                scores=selection.scores,
                settings=self._settings,
                max_units=selection.result_limit,
                space_scoped=self._space_scoped_expand(),
            )
        except Exception:
            logger.exception(
                "Knowledge retrieval failed",
                extra={"tenant_id": context.tenant_id, "agent_id": context.agent_id},
            )
            return KnowledgeEvidenceBundle(
                status="unavailable", duration_ms=runtime_helpers.duration_ms(started)
            )
        if not evidence:
            return KnowledgeEvidenceBundle(
                status="no_results",
                retrieval_method=selection.retrieval_method,
                candidate_count=len(selection.ranked_ids),
                duration_ms=runtime_helpers.duration_ms(started),
                embed_duration_ms=embed_duration_ms,
                space_count=space_count,
                degradation_reasons=selection.degradation_reasons,
            )
        items = tuple(
            self._evidence_item(row, selection, media_refs.get(row[0].id, ())) for row in evidence
        )
        return KnowledgeEvidenceBundle(
            content=runtime_helpers.render_evidence(
                [
                    (item.citation_id, item.title, item.citation_anchor, item.excerpt)
                    for item in items
                ]
            ),
            citation_ids=tuple(item.citation_id for item in items),
            items=items,
            status="degraded" if selection.degradation_reasons else "ok",
            retrieval_method=selection.retrieval_method,
            candidate_count=len(selection.ranked_ids),
            duration_ms=runtime_helpers.duration_ms(started),
            embed_duration_ms=embed_duration_ms,
            space_count=space_count,
            degradation_reasons=selection.degradation_reasons,
        )

    def _space_scoped_expand(self) -> bool:
        return False

    async def _legacy_candidates(
        self, context: KnowledgeRuntimeContext, limit: int
    ) -> KnowledgeCandidateSelection:
        candidate_limit = min(limit * self._candidate_multiplier, 60)
        lexical_ids, space_ids = await self._lexical_candidates(context, candidate_limit)
        semantic_ids, method = await self._legacy_semantic_candidates(
            context, space_ids, candidate_limit
        )
        ranked = runtime_helpers.reciprocal_rank_fusion(
            lexical_ids, semantic_ids, self._reciprocal_rank_constant, limit
        )
        return KnowledgeCandidateSelection(
            ranked,
            runtime_helpers.rank_scores((lexical_ids, semantic_ids)),
            method,
            {},
            ("semantic_service_unavailable",) if method == "lexical_fallback" else (),
            runtime_helpers.candidate_sources(lexical_ids, semantic_ids),
        )

    async def _configured_candidates(
        self, context: KnowledgeRuntimeContext, limit: int
    ) -> tuple[KnowledgeCandidateSelection, int, int]:
        spaces, embeddings, rerankers = await self._configured_profiles(context)
        embed_started = perf_counter()
        vectors = await self._query_vectors(context, spaces, embeddings)
        embed_duration_ms = runtime_helpers.duration_ms(embed_started)
        ranked_spaces = await self._rank_configured_spaces(
            context, spaces, embeddings, rerankers, vectors
        )
        selection = await self._select_configured_candidates(context, ranked_spaces, limit)
        return selection, embed_duration_ms, len(spaces)

    async def _rank_configured_spaces(
        self,
        context: KnowledgeRuntimeContext,
        spaces: tuple[KnowledgeSpace, ...],
        embeddings: dict[str, EmbeddingConfig],
        rerankers: dict[str, RerankerConfig],
        vectors: dict[str, tuple[float, ...]],
    ) -> tuple[_SpaceRanking, ...]:
        semaphore = asyncio.Semaphore(_MAX_PARALLEL_SPACES)

        async def rank(space: KnowledgeSpace) -> _SpaceRanking:
            async with semaphore:
                return await self._rank_space(
                    context,
                    space,
                    embeddings,
                    rerankers,
                    vectors.get(space.embedding_config_id)
                    if space.embedding_config_id is not None
                    else None,
                )

        return tuple(await asyncio.gather(*(rank(space) for space in spaces)))

    async def _select_configured_candidates(
        self,
        context: KnowledgeRuntimeContext,
        ranked_spaces: tuple[_SpaceRanking, ...],
        limit: int,
    ) -> KnowledgeCandidateSelection:
        rankings = [item.ranking for item in ranked_spaces]
        provenance, degradation_reasons, match_sources, vector_scores = self._ranking_metadata(
            ranked_spaces
        )
        merge_settings = await self._eligible_merge_settings(context, ranked_spaces)
        merge_ready = (
            merge_settings is not None
            and merge_settings.merge_rerank_enabled
            and merge_settings.reranker_config_id is not None
        )
        effective_rankings = (
            [item.ranking[:MERGE_PER_SPACE_CANDIDATE_CAP] for item in ranked_spaces]
            if merge_ready
            else rankings
        )
        rrf_limit = (
            max(limit, merge_settings.rerank_top_n)
            if merge_ready and merge_settings is not None
            else limit
        )
        ranked = runtime_helpers.reciprocal_rank_fusion_many(
            effective_rankings, self._reciprocal_rank_constant, rrf_limit
        )
        used_merge_rerank = False
        result_limit = None
        if merge_ready and merge_settings is not None:
            result_limit = final_limit = min(limit, merge_settings.result_top_k)
            merged, merge_reason = await self._merge_rerank(
                context, merge_settings, ranked, final_limit
            )
            ranked = merged
            if merge_reason is None:
                used_merge_rerank = True
            else:
                degradation_reasons.add(merge_reason)
        elif rrf_limit > limit:
            ranked = ranked[:limit]
        method = runtime_helpers.aggregate_method(
            any(item.used_semantic for item in ranked_spaces),
            any(item.used_reranking for item in ranked_spaces) or used_merge_rerank,
            bool(degradation_reasons),
            merge_reranked=used_merge_rerank,
        )
        return KnowledgeCandidateSelection(
            ranked,
            runtime_helpers.rank_scores(tuple(effective_rankings), self._reciprocal_rank_constant),
            method,
            provenance,
            tuple(sorted(degradation_reasons)),
            match_sources,
            vector_scores,
            result_limit,
        )

    async def _eligible_merge_settings(
        self, context: KnowledgeRuntimeContext, ranked_spaces: tuple[_SpaceRanking, ...]
    ) -> KnowledgeMergeSettings | None:
        spaces_with_hits = sum(1 for item in ranked_spaces if item.ranking)
        if spaces_with_hits < MERGE_MINIMUM_SPACE_HITS:
            return None
        return await self._load_merge_settings(context.tenant_id)

    @staticmethod
    def _ranking_metadata(ranked_spaces: tuple[_SpaceRanking, ...]):
        provenance = {item.space_id: item.provenance for item in ranked_spaces}
        degradation_reasons = {
            reason for item in ranked_spaces for reason in item.degradation_reasons
        }
        match_sources: dict[str, tuple[KnowledgeMatchSource, ...]] = {}
        vector_scores: dict[str, float] = {}
        for item in ranked_spaces:
            match_sources.update(item.match_sources)
            vector_scores.update(item.vector_scores)
        return provenance, degradation_reasons, match_sources, vector_scores

    async def _load_merge_settings(self, tenant_id: str) -> KnowledgeMergeSettings | None:
        return await self._merge_runtime_or_raise().load_settings(tenant_id)

    async def _merge_rerank(
        self,
        context: KnowledgeRuntimeContext,
        settings: KnowledgeMergeSettings,
        ranking: tuple[str, ...],
        final_limit: int,
    ) -> tuple[tuple[str, ...], str | None]:
        return await self._merge_runtime_or_raise().rerank(context, settings, ranking, final_limit)

    def _merge_runtime_or_raise(self) -> KnowledgeMergeRuntime:
        if self._merge_runtime is None:
            raise RuntimeError("Knowledge merge runtime is unavailable")
        return self._merge_runtime

    async def _query_vectors(
        self,
        context: KnowledgeRuntimeContext,
        spaces: tuple[KnowledgeSpace, ...],
        embeddings: dict[str, EmbeddingConfig],
    ) -> dict[str, tuple[float, ...]]:
        vectors: dict[str, tuple[float, ...]] = {}
        for space in spaces:
            config_id = space.embedding_config_id
            if config_id is None or config_id in vectors:
                continue
            embedding = embeddings.get(config_id)
            if self._semantic_skip_reason(space, embedding) is not None or embedding is None:
                continue
            try:
                settings = self._settings_or_raise()
                vector = await ConfiguredKnowledgeEmbedding(
                    settings, self._cipher_or_raise(), embedding
                ).embed((context.query.strip(),))
                vectors[config_id] = tuple(vector[0])
            except Exception:
                logger.exception(
                    "Knowledge query embedding failed; spaces will fall back to lexical",
                    extra={"tenant_id": context.tenant_id, "agent_id": context.agent_id},
                )
        return vectors

    async def _rank_space(
        self,
        context: KnowledgeRuntimeContext,
        space: KnowledgeSpace,
        embeddings: dict[str, EmbeddingConfig],
        rerankers: dict[str, RerankerConfig],
        query_vector: tuple[float, ...] | None,
    ) -> _SpaceRanking:
        candidate_limit = max(1, min(space.candidate_top_k, 60))
        lexical = await self._lexical_candidates_in_space(context, space.id, candidate_limit)
        semantic: tuple[str, ...] = ()
        embedding = embeddings.get(space.embedding_config_id) if space.embedding_config_id else None
        reason = self._semantic_skip_reason(space, embedding)
        semantic_ready = False
        vector_scores: dict[str, float] = {}
        if reason is None and embedding is not None and query_vector is not None:
            try:
                settings = self._settings_or_raise()
                hits = await MilvusKnowledgeVectorStore(
                    settings,
                    collection=runtime_helpers.collection_name(settings, embedding.id),
                    embedding_dimension=embedding.embedding_dimension,
                ).search_scored(
                    query_vector,
                    KnowledgeVectorSearchScope(context.tenant_id, (space.id,)),
                    candidate_limit,
                )
                accepted_hits = tuple(
                    hit
                    for hit in hits
                    if space.min_vector_score is None or hit.score >= space.min_vector_score
                )
                semantic = tuple(hit.chunk_id for hit in accepted_hits)
                vector_scores = {hit.chunk_id: hit.score for hit in accepted_hits}
                semantic_ready = True
            except Exception:
                reason = "embedding_or_vector_service_unavailable"
                logger.exception(
                    "Knowledge semantic retrieval failed; using lexical candidates",
                    extra={"tenant_id": context.tenant_id, "agent_id": context.agent_id},
                )
        elif reason is None and embedding is not None and query_vector is None:
            reason = "embedding_or_vector_service_unavailable"
        ranking = runtime_helpers.reciprocal_rank_fusion(
            lexical, semantic, self._reciprocal_rank_constant, candidate_limit
        )
        reranker = rerankers.get(space.reranker_config_id) if space.reranker_config_id else None
        rerank_reason = None
        used_reranking = False
        if semantic_ready:
            ranking, rerank_reason = await self._rerank_if_enabled(
                context, space, reranker, ranking
            )
            used_reranking = space.rerank_enabled and rerank_reason is None
        degradation = {item for item in (reason, rerank_reason) if item}
        return _SpaceRanking(
            space_id=space.id,
            ranking=ranking,
            provenance=KnowledgeRetrievalProvenance(
                retrieval_method=runtime_helpers.space_method(
                    semantic_ready, space.rerank_enabled, reason, rerank_reason
                ),
                embedding_config_name=runtime_helpers.config_label(embedding),
                reranker_config_name=runtime_helpers.config_label(reranker),
                degradation_reason=runtime_helpers.combined_reason(reason, rerank_reason),
            ),
            degradation_reasons=degradation,
            match_sources=runtime_helpers.candidate_sources(lexical, semantic),
            vector_scores=vector_scores,
            used_semantic=semantic_ready,
            used_reranking=used_reranking,
        )

    async def _rerank_if_enabled(
        self,
        context: KnowledgeRuntimeContext,
        space: KnowledgeSpace,
        reranker: RerankerConfig | None,
        ranking: tuple[str, ...],
    ) -> tuple[tuple[str, ...], str | None]:
        if not space.rerank_enabled:
            return ranking, None
        if not space.reranker_config_id:
            return ranking, "reranker_config_unavailable"
        if reranker is None:
            return ranking, "reranker_config_unavailable"
        evidence = await self._authorized_evidence(context, ranking)
        if not evidence:
            return (), None
        try:
            results = await ConfiguredReranker(
                self._settings_or_raise(), self._cipher_or_raise(), reranker
            ).rerank(
                context.query.strip(),
                tuple(
                    runtime_helpers.bounded(chunk.content, 2_000)
                    for chunk, _document, _version in evidence
                ),
                min(space.rerank_top_n, len(evidence)),
            )
        except Exception:
            logger.exception(
                "Knowledge reranking failed; using pre-rerank candidates",
                extra={"tenant_id": context.tenant_id, "agent_id": context.agent_id},
            )
            return ranking, "reranker_service_unavailable"
        ranked = tuple(
            evidence[item.index][0].id
            for item in results
            if space.min_rerank_score is None or item.score >= space.min_rerank_score
        )
        return ranked, None

    async def _configured_profiles(
        self, context: KnowledgeRuntimeContext
    ) -> tuple[tuple[KnowledgeSpace, ...], dict[str, EmbeddingConfig], dict[str, RerankerConfig]]:
        async with self._database.session() as session:
            await self._database.set_tenant(session, context.tenant_id)
            repository = KnowledgeRuntimeRepository(session)
            spaces = await repository.active_spaces(context.tenant_id, context.agent_id)
            embeddings, rerankers = await load_retrieval_profiles(
                session, context.tenant_id, spaces
            )
            return spaces, embeddings, rerankers

    def _semantic_skip_reason(
        self, space: KnowledgeSpace, embedding: EmbeddingConfig | None
    ) -> str | None:
        if space.embedding_config_id is None:
            return None
        if self._settings is None or knowledge_vector_runtime_issue(self._settings):
            return "vector_runtime_unavailable"
        if getattr(space, "retrieval_index_status", "ready") != "ready":
            return "vector_index_not_ready"
        if embedding is None:
            return "embedding_config_unavailable"
        if not embedding_snapshot_matches(space, embedding):
            return "embedding_config_snapshot_mismatch"
        return None

    async def _lexical_candidates(
        self, context: KnowledgeRuntimeContext, limit: int
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        async with self._database.session() as session:
            await self._database.set_tenant(session, context.tenant_id)
            repository = KnowledgeRuntimeRepository(session)
            space_ids = await repository.active_space_ids(context.tenant_id, context.agent_id)
            evidence = await repository.lexical_search(
                context.tenant_id, context.agent_id, context.query.strip(), limit
            )
            return tuple(item[0].id for item in evidence), space_ids

    async def _lexical_candidates_in_space(
        self, context: KnowledgeRuntimeContext, space_id: str, limit: int
    ) -> tuple[str, ...]:
        async with self._database.session() as session:
            await self._database.set_tenant(session, context.tenant_id)
            evidence = await KnowledgeRuntimeRepository(session).lexical_search_in_space(
                context.tenant_id, context.agent_id, space_id, context.query.strip(), limit
            )
            return tuple(item[0].id for item in evidence)

    async def _legacy_semantic_candidates(
        self,
        context: KnowledgeRuntimeContext,
        space_ids: tuple[str, ...],
        limit: int,
    ) -> tuple[tuple[str, ...], str]:
        if self._retrieval_mode != "hybrid" or self._semantic_search is None:
            return (), "lexical"
        try:
            result = await self._semantic_search.search(
                context.tenant_id, space_ids, context.query.strip(), limit
            )
            return result, "hybrid"
        except Exception:
            logger.exception(
                "Knowledge semantic retrieval failed; using lexical candidates",
                extra={"tenant_id": context.tenant_id, "agent_id": context.agent_id},
            )
            return (), "lexical_fallback"

    async def _authorized_evidence(
        self, context: KnowledgeRuntimeContext, chunk_ids: tuple[str, ...]
    ) -> list[KnowledgeEvidenceRow]:
        async with self._database.session() as session:
            await self._database.set_tenant(session, context.tenant_id)
            return await KnowledgeRuntimeRepository(session).authorized_candidates(
                context.tenant_id, context.agent_id, chunk_ids
            )

    @staticmethod
    def _evidence_item(
        row: KnowledgeEvidenceRow,
        selection: KnowledgeCandidateSelection,
        media_refs: tuple[KnowledgeMediaRef, ...] = (),
    ) -> KnowledgeEvidenceItem:
        chunk, document, version = row
        space_id = getattr(chunk, "space_id", "")
        provenance = selection.provenance_by_space.get(
            space_id, KnowledgeRetrievalProvenance(selection.retrieval_method)
        )
        return KnowledgeEvidenceItem(
            citation_id=chunk.id,
            title=document.title,
            citation_anchor=chunk.citation_anchor,
            space_id=space_id,
            retrieval_method=provenance.retrieval_method,
            score=selection.scores.get(chunk.id, 0.0),
            excerpt=runtime_helpers.bounded(chunk.content, 800),
            document_id=getattr(document, "id", ""),
            document_version_id=getattr(version, "id", ""),
            content_chars=len(chunk.content),
            embedding_config_name=provenance.embedding_config_name,
            reranker_config_name=provenance.reranker_config_name,
            degradation_reason=provenance.degradation_reason,
            match_sources=selection.match_sources_by_chunk.get(chunk.id, ()),
            vector_score=selection.vector_scores_by_chunk.get(chunk.id),
            slide_no=getattr(chunk, "slide_no", None),
            group_id=getattr(chunk, "group_id", None),
            media_refs=media_refs,
        )

    def _cipher_or_raise(self) -> CredentialCipher:
        if self._cipher is None:
            raise RuntimeError("Knowledge credential cipher is unavailable")
        return self._cipher

    def _settings_or_raise(self) -> AppConfig:
        if self._settings is None:
            raise RuntimeError("Knowledge settings are unavailable")
        return self._settings
