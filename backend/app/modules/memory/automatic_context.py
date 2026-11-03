from __future__ import annotations

import logging
from typing import Protocol

from app.core.config import MemoryRuntimeSection
from app.infrastructure.db.session import DatabaseManager
from app.modules.memory.context import (
    MemoryContextItem,
    MemoryRecallContext,
    bounded_memory_items,
    build_memory_item_context,
    memory_context_items,
)
from app.modules.memory.models import MemoryRecord
from app.modules.memory.queries import visible_memory_statement
from app.modules.memory.retrieval import MemoryRetrievalService, SemanticMemorySearchPort
from app.modules.memory.runtime_contract import PINNED_MEMORY_TYPES

logger = logging.getLogger(__name__)
_PINNED_MAX_TOKENS = 400


class AutomaticMemoryRuntimeContext(Protocol):
    @property
    def tenant_id(self) -> str: ...

    @property
    def agent_id(self) -> str: ...

    @property
    def actor_id(self) -> str: ...

    @property
    def interaction_id(self) -> str: ...

    @property
    def conversation_id(self) -> str | None: ...


class AutomaticMemoryContextService:
    """Builds small pre-understanding memory and query-aware post-understanding recall."""

    def __init__(
            self,
            database: DatabaseManager,
            settings: MemoryRuntimeSection,
            semantic_search: SemanticMemorySearchPort | None,
    ) -> None:
        self._database = database
        self._settings = settings
        self._semantic_search = semantic_search

    async def pinned_for(
            self, context: AutomaticMemoryRuntimeContext
    ) -> tuple[MemoryContextItem, ...]:
        try:
            async with self._database.session() as session:
                await self._database.set_tenant(session, context.tenant_id)
                rows = await session.scalars(
                    visible_memory_statement(
                        tenant_id=context.tenant_id,
                        agent_id=context.agent_id,
                        actor_id=context.actor_id,
                        conversation_id=context.conversation_id,
                        include_pending_owner=False,
                    )
                    .where(
                        MemoryRecord.status == "active",
                        MemoryRecord.requires_confirmation.is_(False),
                        MemoryRecord.memory_type.in_(PINNED_MEMORY_TYPES),
                    )
                    .order_by(MemoryRecord.updated_at.desc(), MemoryRecord.id)
                    .limit(self._settings.context_limit)
                )
            budget = min(self._settings.context_max_tokens, _PINNED_MAX_TOKENS)
            return bounded_memory_items(memory_context_items(tuple(rows)), budget)
        except Exception:
            logger.exception(
                "Pinned runtime memory load failed",
                extra={"tenant_id": context.tenant_id, "interaction_id": context.interaction_id},
            )
            return ()

    async def recall_for(
            self, context: AutomaticMemoryRuntimeContext, query: str
    ) -> MemoryRecallContext:
        if not query.strip():
            return MemoryRecallContext()
        try:
            async with self._database.session() as session:
                await self._database.set_tenant(session, context.tenant_id)
                result = await MemoryRetrievalService(
                    session,
                    self._semantic_search,
                    candidate_limit=min(self._settings.search_limit * 4, 100),
                    include_pending_owner=False,
                    active_only=True,
                ).retrieve(context, query)
            items = bounded_memory_items(
                memory_context_items(result.records), self._settings.context_max_tokens
            )
            return MemoryRecallContext(
                items=items,
                retrieval_method=result.retrieval_method,
                degradation_reason=result.degradation_reason,
            )
        except Exception:
            logger.exception(
                "Query-aware runtime memory recall failed",
                extra={"tenant_id": context.tenant_id, "interaction_id": context.interaction_id},
            )
            return MemoryRecallContext(
                retrieval_method="lexical_fallback",
                degradation_reason="memory_recall_unavailable",
            )

    def render(self, items: tuple[MemoryContextItem, ...]) -> str:
        return build_memory_item_context(items, self._settings.context_max_tokens)
