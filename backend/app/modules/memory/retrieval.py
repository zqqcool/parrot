from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from sqlalchemy import and_, asc, desc, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.memory.models import MemoryRecord
from app.modules.memory.queries import visible_memory_statement


class MemorySearchContext(Protocol):
    @property
    def tenant_id(self) -> str: ...

    @property
    def agent_id(self) -> str: ...

    @property
    def actor_id(self) -> str | None: ...

    @property
    def conversation_id(self) -> str | None: ...


@dataclass(frozen=True)
class SemanticMemoryCandidates:
    ids: tuple[str, ...]
    available: bool


class SemanticMemorySearchPort(Protocol):
    async def search(
        self, context: MemorySearchContext, query: str, limit: int
    ) -> SemanticMemoryCandidates: ...


@dataclass(frozen=True)
class MemoryRetrievalResult:
    records: tuple[MemoryRecord, ...]
    anchor_id: str | None
    retrieval_method: Literal["hybrid", "lexical", "lexical_fallback"]
    degradation_reason: str | None


class MemoryRetrievalService:
    """Retrieve one relevant memory and its tenant-safe chronological context."""

    def __init__(
        self,
        session: AsyncSession,
        semantic_search: SemanticMemorySearchPort | None,
        *,
        candidate_limit: int,
        reciprocal_rank_constant: int = 60,
        neighbor_count: int = 5,
        include_pending_owner: bool = True,
        active_only: bool = False,
    ) -> None:
        self._session = session
        self._semantic_search = semantic_search
        self._candidate_limit = candidate_limit
        self._reciprocal_rank_constant = reciprocal_rank_constant
        self._neighbor_count = neighbor_count
        self._include_pending_owner = include_pending_owner
        self._active_only = active_only

    async def retrieve(self, context: MemorySearchContext, query: str) -> MemoryRetrievalResult:
        lexical_ids = await self._lexical_ids(context, query)
        semantic = await self._semantic_candidates(context, query)
        ranked = reciprocal_rank_fusion(lexical_ids, semantic.ids, self._reciprocal_rank_constant)
        anchor = await self._anchor(context, ranked)
        method, reason = _method(semantic, self._semantic_search is not None)
        if anchor is None:
            return MemoryRetrievalResult((), None, method, reason)
        records = await self._context_window(context, anchor)
        return MemoryRetrievalResult(records, anchor.id, method, reason)

    async def _lexical_ids(self, context: MemorySearchContext, query: str) -> tuple[str, ...]:
        terms = func.websearch_to_tsquery("simple", query)
        rank = func.ts_rank_cd(MemoryRecord.search_vector, terms)
        rows = await self._session.scalars(
            self._visible(context)
            .where(MemoryRecord.search_vector.op("@@")(terms))
            .order_by(desc(rank), MemoryRecord.id)
            .limit(self._candidate_limit)
        )
        return tuple(item.id for item in rows)

    async def _semantic_candidates(
        self, context: MemorySearchContext, query: str
    ) -> SemanticMemoryCandidates:
        if self._semantic_search is None:
            return SemanticMemoryCandidates((), True)
        return await self._semantic_search.search(context, query, self._candidate_limit)

    async def _anchor(
        self, context: MemorySearchContext, ranked_ids: tuple[str, ...]
    ) -> MemoryRecord | None:
        if not ranked_ids:
            return None
        rows = await self._session.scalars(
            self._visible(context).where(MemoryRecord.id.in_(ranked_ids))
        )
        by_id = {item.id: item for item in rows}
        return next((by_id[item_id] for item_id in ranked_ids if item_id in by_id), None)

    async def _context_window(
        self, context: MemorySearchContext, anchor: MemoryRecord
    ) -> tuple[MemoryRecord, ...]:
        agent_filter = (
            MemoryRecord.agent_id.is_(None)
            if anchor.agent_id is None
            else MemoryRecord.agent_id == anchor.agent_id
        )
        statement = self._visible(context).where(
            MemoryRecord.scope_type == anchor.scope_type,
            MemoryRecord.scope_id == anchor.scope_id,
            agent_filter,
        )
        before = await self._session.scalars(
            statement.where(_before(anchor))
            .order_by(desc(MemoryRecord.created_at), desc(MemoryRecord.id))
            .limit(self._neighbor_count)
        )
        after = await self._session.scalars(
            statement.where(_after(anchor))
            .order_by(asc(MemoryRecord.created_at), asc(MemoryRecord.id))
            .limit(self._neighbor_count)
        )
        return tuple(reversed(tuple(before))) + (anchor,) + tuple(after)

    def _visible(self, context: MemorySearchContext):
        statement = visible_memory_statement(
            tenant_id=context.tenant_id,
            agent_id=context.agent_id,
            actor_id=context.actor_id,
            conversation_id=context.conversation_id,
            include_pending_owner=self._include_pending_owner,
        )
        if self._active_only:
            statement = statement.where(
                MemoryRecord.status == "active",
                MemoryRecord.requires_confirmation.is_(False),
            )
        return statement


def _before(anchor: MemoryRecord):
    return or_(
        MemoryRecord.created_at < anchor.created_at,
        and_(MemoryRecord.created_at == anchor.created_at, MemoryRecord.id < anchor.id),
    )


def _after(anchor: MemoryRecord):
    return or_(
        MemoryRecord.created_at > anchor.created_at,
        and_(MemoryRecord.created_at == anchor.created_at, MemoryRecord.id > anchor.id),
    )


def reciprocal_rank_fusion(
    lexical_ids: tuple[str, ...], semantic_ids: tuple[str, ...], constant: int
) -> tuple[str, ...]:
    scores: dict[str, float] = {}
    first_rank: dict[str, int] = {}
    for ranking in (lexical_ids, semantic_ids):
        for index, item_id in enumerate(ranking, start=1):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (constant + index)
            first_rank[item_id] = min(first_rank.get(item_id, index), index)
    return tuple(
        sorted(scores, key=lambda item_id: (-scores[item_id], first_rank[item_id], item_id))
    )


def _method(
    semantic: SemanticMemoryCandidates, semantic_configured: bool
) -> tuple[Literal["hybrid", "lexical", "lexical_fallback"], str | None]:
    if not semantic_configured:
        return "lexical", None
    if not semantic.available:
        return "lexical_fallback", "semantic_search_unavailable"
    return "hybrid", None
