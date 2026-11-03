from __future__ import annotations

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from app.core.agent_types import AgentTypeKey
from app.modules.agents.models import AgentPublication
from app.modules.knowledge.models import (
    AgentKnowledgeSpaceBinding,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeDocumentVersion,
    KnowledgeSpace,
)
from app.modules.knowledge.runtime_helpers import lexical_query_variants

KnowledgeEvidenceRow = tuple[KnowledgeChunk, KnowledgeDocument, KnowledgeDocumentVersion]


class KnowledgeRuntimeRepository:
    """Live read model for Agent retrieval and service-authorized space tests."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def active_space_ids(self, tenant_id: str, agent_id: str) -> tuple[str, ...]:
        return tuple(item.id for item in await self.active_spaces(tenant_id, agent_id))

    async def active_spaces(self, tenant_id: str, agent_id: str) -> tuple[KnowledgeSpace, ...]:
        rows = await self.session.scalars(
            select(KnowledgeSpace)
            .join(
                AgentKnowledgeSpaceBinding,
                (AgentKnowledgeSpaceBinding.tenant_id == KnowledgeSpace.tenant_id)
                & (AgentKnowledgeSpaceBinding.space_id == KnowledgeSpace.id),
            )
            .join(
                AgentPublication,
                (AgentPublication.tenant_id == AgentKnowledgeSpaceBinding.tenant_id)
                & (AgentPublication.id == AgentKnowledgeSpaceBinding.agent_id),
            )
            .where(
                KnowledgeSpace.tenant_id == tenant_id,
                AgentKnowledgeSpaceBinding.agent_id == agent_id,
                AgentPublication.agent_type_key == AgentTypeKey.KNOWLEDGE,
                AgentPublication.status == "active",
                AgentPublication.published.is_(True),
                KnowledgeSpace.status == "active",
            )
            .order_by(KnowledgeSpace.id)
        )
        return tuple(rows)

    async def active_space(self, tenant_id: str, space_id: str) -> KnowledgeSpace | None:
        return await self.session.scalar(
            select(KnowledgeSpace).where(
                KnowledgeSpace.tenant_id == tenant_id,
                KnowledgeSpace.id == space_id,
                KnowledgeSpace.status == "active",
            )
        )

    async def lexical_search(
        self, tenant_id: str, agent_id: str, query: str, limit: int
    ) -> list[KnowledgeEvidenceRow]:
        return await self._run_lexical_search(
            self.authorized_statement(tenant_id, agent_id), query, limit
        )

    async def lexical_search_in_space(
        self, tenant_id: str, agent_id: str, space_id: str, query: str, limit: int
    ) -> list[KnowledgeEvidenceRow]:
        return await self._run_lexical_search(
            self.authorized_statement(tenant_id, agent_id).where(
                KnowledgeChunk.space_id == space_id
            ),
            query,
            limit,
        )

    async def lexical_search_for_space(
        self, tenant_id: str, space_id: str, query: str, limit: int
    ) -> list[KnowledgeEvidenceRow]:
        return await self._run_lexical_search(
            self.published_space_statement(tenant_id, space_id), query, limit
        )

    async def _run_lexical_search(
        self,
        statement: Select[tuple[KnowledgeChunk, KnowledgeDocument, KnowledgeDocumentVersion]],
        query: str,
        limit: int,
    ) -> list[KnowledgeEvidenceRow]:
        for variant in lexical_query_variants(query):
            terms = func.websearch_to_tsquery("simple", variant)
            rank = func.ts_rank_cd(KnowledgeChunk.search_vector, terms)
            rows = await self.session.execute(
                statement.where(KnowledgeChunk.search_vector.op("@@")(terms))
                .order_by(desc(rank), KnowledgeChunk.id)
                .limit(limit)
            )
            results = list(rows.tuples())
            if results:
                return results
        return []

    async def authorized_candidates(
        self,
        tenant_id: str,
        agent_id: str,
        chunk_ids: tuple[str, ...],
    ) -> list[KnowledgeEvidenceRow]:
        if not chunk_ids:
            return []
        rows = await self.session.execute(
            self.authorized_statement(tenant_id, agent_id).where(KnowledgeChunk.id.in_(chunk_ids))
        )
        by_id = {chunk.id: (chunk, document, version) for chunk, document, version in rows.tuples()}
        return [by_id[item] for item in chunk_ids if item in by_id]

    async def published_candidates_for_space(
        self, tenant_id: str, space_id: str, chunk_ids: tuple[str, ...]
    ) -> list[KnowledgeEvidenceRow]:
        if not chunk_ids:
            return []
        rows = await self.session.execute(
            self.published_space_statement(tenant_id, space_id).where(
                KnowledgeChunk.id.in_(chunk_ids)
            )
        )
        by_id = {chunk.id: (chunk, document, version) for chunk, document, version in rows.tuples()}
        return [by_id[item] for item in chunk_ids if item in by_id]

    @staticmethod
    def published_space_statement(
        tenant_id: str, space_id: str
    ) -> Select[tuple[KnowledgeChunk, KnowledgeDocument, KnowledgeDocumentVersion]]:
        return (
            select(KnowledgeChunk, KnowledgeDocument, KnowledgeDocumentVersion)
            .select_from(KnowledgeChunk)
            .join(
                KnowledgeSpace,
                (KnowledgeSpace.tenant_id == KnowledgeChunk.tenant_id)
                & (KnowledgeSpace.id == KnowledgeChunk.space_id),
            )
            .join(
                KnowledgeDocumentVersion,
                (KnowledgeDocumentVersion.tenant_id == KnowledgeChunk.tenant_id)
                & (KnowledgeDocumentVersion.id == KnowledgeChunk.document_version_id),
            )
            .join(
                KnowledgeDocument,
                (KnowledgeDocument.tenant_id == KnowledgeDocumentVersion.tenant_id)
                & (KnowledgeDocument.id == KnowledgeDocumentVersion.document_id),
            )
            .where(
                KnowledgeChunk.tenant_id == tenant_id,
                KnowledgeChunk.space_id == space_id,
                KnowledgeSpace.status == "active",
                KnowledgeDocument.status == "active",
                KnowledgeDocumentVersion.status == "published",
            )
        )

    @staticmethod
    def authorized_statement(
        tenant_id: str, agent_id: str
    ) -> Select[tuple[KnowledgeChunk, KnowledgeDocument, KnowledgeDocumentVersion]]:
        return (
            select(KnowledgeChunk, KnowledgeDocument, KnowledgeDocumentVersion)
            .select_from(KnowledgeChunk)
            .join(
                AgentKnowledgeSpaceBinding,
                (AgentKnowledgeSpaceBinding.tenant_id == KnowledgeChunk.tenant_id)
                & (AgentKnowledgeSpaceBinding.space_id == KnowledgeChunk.space_id),
            )
            .join(
                AgentPublication,
                (AgentPublication.tenant_id == AgentKnowledgeSpaceBinding.tenant_id)
                & (AgentPublication.id == AgentKnowledgeSpaceBinding.agent_id),
            )
            .join(
                KnowledgeSpace,
                (KnowledgeSpace.tenant_id == KnowledgeChunk.tenant_id)
                & (KnowledgeSpace.id == KnowledgeChunk.space_id),
            )
            .join(
                KnowledgeDocumentVersion,
                (KnowledgeDocumentVersion.tenant_id == KnowledgeChunk.tenant_id)
                & (KnowledgeDocumentVersion.id == KnowledgeChunk.document_version_id),
            )
            .join(
                KnowledgeDocument,
                (KnowledgeDocument.tenant_id == KnowledgeDocumentVersion.tenant_id)
                & (KnowledgeDocument.id == KnowledgeDocumentVersion.document_id),
            )
            .where(
                KnowledgeChunk.tenant_id == tenant_id,
                AgentKnowledgeSpaceBinding.tenant_id == tenant_id,
                AgentKnowledgeSpaceBinding.agent_id == agent_id,
                AgentPublication.agent_type_key == AgentTypeKey.KNOWLEDGE,
                AgentPublication.status == "active",
                AgentPublication.published.is_(True),
                KnowledgeSpace.status == "active",
                KnowledgeDocument.status == "active",
                KnowledgeDocumentVersion.status == "published",
            )
        )
