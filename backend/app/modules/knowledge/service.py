from __future__ import annotations

import hashlib

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.config import AppConfig
from app.core.errors import AppError
from app.core.ids import new_id
from app.core.task_dispatch import TaskDispatcher
from app.infrastructure.credential_cipher import CredentialCipher
from app.infrastructure.db.session import DatabaseManager
from app.modules.agents.ports import AgentCatalogPort
from app.modules.audit.service import append_audit
from app.modules.embedding_configs.models import EmbeddingConfig
from app.modules.iam.schemas import PrincipalContext
from app.modules.iam.user_references import UserReferenceResolver
from app.modules.knowledge.access import KnowledgeAccessPolicy
from app.modules.knowledge.chunking import split_content
from app.modules.knowledge.document_list_views import document_list_views
from app.modules.knowledge.document_views import document_view
from app.modules.knowledge.embedding_profile import (
    apply_embedding_snapshot,
    embedding_snapshot_matches,
)
from app.modules.knowledge.models import (
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeDocumentVersion,
    KnowledgeSpace,
)
from app.modules.knowledge.repository import KnowledgeRepository
from app.modules.knowledge.retrieval_validation import validate_retrieval_configs
from app.modules.knowledge.schemas import (
    AgentKnowledgeSearchTestItem,
    AgentKnowledgeSearchTestRequest,
    AgentKnowledgeSearchTestView,
    AgentKnowledgeSpaceBindingsView,
    KnowledgeDocumentCreateRequest,
    KnowledgeDocumentView,
    KnowledgeSearchResult,
    KnowledgeSpaceAgentBindingsView,
    KnowledgeSpaceChunkingUpdateRequest,
    KnowledgeSpaceCreateRequest,
    KnowledgeSpaceGrantsRequest,
    KnowledgeSpaceGrantsView,
    KnowledgeSpaceRetrievalUpdateRequest,
    KnowledgeSpaceView,
    knowledge_media_ref_view,
)
from app.modules.knowledge.space_search_runtime import KnowledgeSpaceSearchRuntime
from app.modules.knowledge.title_normalization import (
    available_title_error,
    is_available_title_conflict,
    normalize_document_title,
)
from app.modules.knowledge.vector_jobs import enqueue_vector_job
from app.modules.knowledge.view_helpers import (
    knowledge_space_view,
    process_manual_content,
    text_processing_settings,
)

SEARCH_EXCERPT_MAX_CHARS = 800


class KnowledgeService:
    def __init__(
        self,
        session: AsyncSession,
        database: DatabaseManager,
        agents: AgentCatalogPort,
        *,
        settings: AppConfig | None = None,
        cipher: CredentialCipher | None = None,
        dispatcher: TaskDispatcher | None = None,
    ) -> None:
        self.session = session
        self.database = database
        self.agents = agents
        self.repository = KnowledgeRepository(session)
        self.access_policy = KnowledgeAccessPolicy(session, database)
        self.settings = settings
        self.cipher = cipher
        self.dispatcher = dispatcher

    async def list_spaces(
        self, principal: PrincipalContext, tenant_id: str, *, query: str | None = None
    ) -> list[KnowledgeSpaceView]:
        await self._enter(principal, tenant_id, "knowledge.spaces.read")
        spaces = await self.repository.list_spaces(tenant_id, query=query)
        visible = [
            item
            for item in spaces
            if item.status == "active"
            and await self.repository.user_has_access(tenant_id, item.id, principal.subject_id)
        ]
        return [knowledge_space_view(item) for item in visible]

    async def create_space(
        self, principal: PrincipalContext, tenant_id: str, payload: KnowledgeSpaceCreateRequest
    ) -> KnowledgeSpaceView:
        await self._enter(principal, tenant_id, "knowledge.spaces.manage")
        embedding = await self._validate_retrieval_configs(tenant_id, payload)
        space_id = new_id("knowledge_space")
        item = KnowledgeSpace(
            id=space_id,
            tenant_id=tenant_id,
            slug=space_id,
            name=payload.name.strip(),
            classification=payload.classification,
            chunk_separator=payload.chunk_separator,
            chunk_size_chars=payload.chunk_size_chars,
            chunk_overlap_chars=payload.chunk_overlap_chars,
            normalize_whitespace=payload.text_processing.normalize_whitespace,
            remove_urls_and_emails=payload.text_processing.remove_urls_and_emails,
            embedding_config_id=payload.embedding_config_id,
            retrieval_index_status=(
                "pending" if payload.embedding_config_id is not None else "not_configured"
            ),
            created_by_user_id=principal.subject_id,
        )
        if embedding is not None:
            apply_embedding_snapshot(item, embedding)
        self.session.add(item)
        await self.session.flush()
        await self.repository.replace_grants(tenant_id, item.id, (principal.subject_id,), ())
        append_audit(
            self.session,
            principal,
            "knowledge.space.create",
            "knowledge_space",
            item.id,
            tenant_id=tenant_id,
        )
        return knowledge_space_view(item)

    async def update_space_chunking(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        space_id: str,
        payload: KnowledgeSpaceChunkingUpdateRequest,
    ) -> KnowledgeSpaceView:
        space = await self._accessible_space(
            principal, tenant_id, space_id, "knowledge.spaces.manage"
        )
        space.chunk_separator = payload.chunk_separator
        space.chunk_size_chars = payload.chunk_size_chars
        space.chunk_overlap_chars = payload.chunk_overlap_chars
        space.normalize_whitespace = payload.text_processing.normalize_whitespace
        space.remove_urls_and_emails = payload.text_processing.remove_urls_and_emails
        await self.session.flush()
        append_audit(
            self.session,
            principal,
            "knowledge.space.chunking.update",
            "knowledge_space",
            space.id,
            {
                "chunk_separator": space.chunk_separator,
                "chunk_size_chars": space.chunk_size_chars,
                "chunk_overlap_chars": space.chunk_overlap_chars,
                "text_processing": payload.text_processing.model_dump(),
            },
            tenant_id=tenant_id,
        )
        return knowledge_space_view(space)

    async def update_space_retrieval(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        space_id: str,
        payload: KnowledgeSpaceRetrievalUpdateRequest,
    ) -> KnowledgeSpaceView:
        space = await self._accessible_space(
            principal, tenant_id, space_id, "knowledge.spaces.manage"
        )
        if payload.embedding_config_id != space.embedding_config_id:
            raise AppError(
                "KNOWLEDGE_EMBEDDING_LOCKED",
                "Embedding mode is fixed when the knowledge space is created",
                status.HTTP_409_CONFLICT,
            )
        embedding = await self._validate_retrieval_configs(
            tenant_id, payload, allow_disabled_embedding=True
        )
        if embedding is not None and not embedding_snapshot_matches(space, embedding):
            raise AppError(
                "KNOWLEDGE_EMBEDDING_SNAPSHOT_MISMATCH",
                "Embedding config no longer matches the knowledge space snapshot",
                status.HTTP_409_CONFLICT,
            )
        space.candidate_top_k = payload.candidate_top_k
        space.min_vector_score = payload.min_vector_score
        space.rerank_enabled = payload.rerank_enabled
        space.reranker_config_id = payload.reranker_config_id
        space.rerank_top_n = payload.rerank_top_n
        space.min_rerank_score = payload.min_rerank_score
        await self.session.flush()
        append_audit(
            self.session,
            principal,
            "knowledge.space.retrieval.update",
            "knowledge_space",
            space.id,
            {
                "embedding_config_id": space.embedding_config_id,
                "candidate_top_k": space.candidate_top_k,
                "rerank_enabled": space.rerank_enabled,
                "reranker_config_id": space.reranker_config_id,
                "retrieval_index_revision": space.retrieval_index_revision,
                "retrieval_index_status": space.retrieval_index_status,
            },
            tenant_id=tenant_id,
        )
        return knowledge_space_view(space)

    async def get_grants(
        self, principal: PrincipalContext, tenant_id: str, space_id: str
    ) -> KnowledgeSpaceGrantsView:
        space = await self._accessible_space(
            principal, tenant_id, space_id, "knowledge.access.manage"
        )
        users, groups = await self.repository.grants(tenant_id, space.id)
        return KnowledgeSpaceGrantsView(
            user_ids=users, group_ids=groups, access_revision=space.access_revision
        )

    async def replace_grants(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        space_id: str,
        payload: KnowledgeSpaceGrantsRequest,
    ) -> KnowledgeSpaceGrantsView:
        space = await self._accessible_space(
            principal, tenant_id, space_id, "knowledge.access.manage"
        )
        user_ids = tuple(dict.fromkeys(payload.user_ids))
        group_ids = tuple(dict.fromkeys(payload.group_ids))
        if not await self.repository.active_members_exist(tenant_id, user_ids):
            raise AppError(
                "KNOWLEDGE_GRANT_USER_INVALID",
                "Knowledge grant user is unavailable",
                status.HTTP_422_UNPROCESSABLE_CONTENT,
            )
        if not await self.repository.active_groups_exist(tenant_id, group_ids):
            raise AppError(
                "KNOWLEDGE_GRANT_GROUP_INVALID",
                "Knowledge grant group is unavailable",
                status.HTTP_422_UNPROCESSABLE_CONTENT,
            )
        await self.repository.replace_grants(tenant_id, space.id, user_ids, group_ids)
        space.access_revision += 1
        await self.session.flush()
        append_audit(
            self.session,
            principal,
            "knowledge.space.grants.replace",
            "knowledge_space",
            space.id,
            {
                "user_count": len(user_ids),
                "group_count": len(group_ids),
                "access_revision": space.access_revision,
            },
            tenant_id=tenant_id,
        )
        return KnowledgeSpaceGrantsView(
            user_ids=user_ids, group_ids=group_ids, access_revision=space.access_revision
        )

    async def list_documents(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        space_id: str,
        *,
        query: str | None = None,
    ) -> list[KnowledgeDocumentView]:
        await self._accessible_space(principal, tenant_id, space_id, "knowledge.documents.read")
        rows = await self.repository.list_documents(tenant_id, space_id, query=query)
        return await document_list_views(tenant_id, rows, UserReferenceResolver(self.session))

    async def create_document(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        space_id: str,
        payload: KnowledgeDocumentCreateRequest,
    ) -> KnowledgeDocumentView:
        space = await self._accessible_space(
            principal, tenant_id, space_id, "knowledge.documents.manage"
        )
        content = process_manual_content(payload.content, space)
        title = payload.title.strip()
        title_key = normalize_document_title(title)
        await self._ensure_available_title(tenant_id, space_id, title_key)
        document = KnowledgeDocument(
            id=new_id("knowledge_document"),
            tenant_id=tenant_id,
            space_id=space_id,
            title=title,
            title_key=title_key,
            source_uri=payload.source_uri.strip() if payload.source_uri else None,
            created_by_user_id=principal.subject_id,
        )
        version = KnowledgeDocumentVersion(
            id=new_id("knowledge_version"),
            tenant_id=tenant_id,
            document_id=document.id,
            version=1,
            content_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            created_by_user_id=principal.subject_id,
            chunk_separator=space.chunk_separator,
            chunk_size_chars=space.chunk_size_chars,
            chunk_overlap_chars=space.chunk_overlap_chars,
            normalize_whitespace=space.normalize_whitespace,
            remove_urls_and_emails=space.remove_urls_and_emails,
            content=content,
        )
        chunks = split_content(
            content,
            space.chunk_size_chars,
            space.chunk_overlap_chars,
            space.chunk_separator,
        )
        self.session.add_all((document, version))
        try:
            await self.session.flush()
        except IntegrityError as exc:
            if is_available_title_conflict(exc):
                raise available_title_error() from exc
            raise
        self.session.add_all(
            KnowledgeChunk(
                id=new_id("knowledge_chunk"),
                tenant_id=tenant_id,
                space_id=space_id,
                document_version_id=version.id,
                ordinal=ordinal,
                content=chunk,
                citation_anchor=f"chunk-{ordinal}",
                search_vector=func.to_tsvector("simple", chunk),
            )
            for ordinal, chunk in enumerate(chunks, start=1)
        )
        await self.session.flush()
        if space.embedding_config_id is not None:
            await enqueue_vector_job(
                self.session, tenant_id, version.id, "upsert", dispatcher=self.dispatcher
            )
        append_audit(
            self.session,
            principal,
            "knowledge.document.create",
            "knowledge_document",
            document.id,
            {
                "space_id": space_id,
                "version": 1,
                "chunk_count": len(chunks),
                "text_processing": text_processing_settings(space).model_dump(),
            },
            tenant_id=tenant_id,
        )
        return document_view(document, 1, len(chunks), principal.display_name)

    async def search(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        space_id: str,
        query: str,
    ) -> list[KnowledgeSearchResult]:
        space = await self._accessible_space(principal, tenant_id, space_id, "knowledge.query")
        normalized = query.strip()
        if not normalized:
            raise AppError(
                "KNOWLEDGE_QUERY_INVALID",
                "Knowledge query is required",
                status.HTTP_422_UNPROCESSABLE_CONTENT,
            )
        if self.settings is None or self.cipher is None:
            raise AppError(
                "KNOWLEDGE_RETRIEVAL_UNAVAILABLE",
                "Knowledge retrieval runtime is unavailable",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        result = await KnowledgeSpaceSearchRuntime(
            self.database,
            candidate_multiplier=self.settings.knowledge.vector.candidate_multiplier,
            reciprocal_rank_constant=self.settings.knowledge.vector.reciprocal_rank_constant,
            settings=self.settings,
            cipher=self.cipher,
        ).search(tenant_id, space.id, normalized, space.candidate_top_k)
        if result.status == "unavailable":
            raise AppError(
                "KNOWLEDGE_RETRIEVAL_UNAVAILABLE",
                "Knowledge retrieval is unavailable",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return [
            KnowledgeSearchResult(
                chunk_id=item.citation_id,
                document_id=item.document_id,
                document_version_id=item.document_version_id,
                title=item.title,
                citation_anchor=item.citation_anchor,
                content_chars=item.content_chars,
                score=item.score,
                excerpt=item.excerpt,
                excerpt_truncated=item.content_chars > SEARCH_EXCERPT_MAX_CHARS,
                retrieval_method=item.retrieval_method,
                embedding_config_name=item.embedding_config_name,
                reranker_config_name=item.reranker_config_name,
                degradation_reason=item.degradation_reason,
                match_sources=item.match_sources,
                vector_score=item.vector_score,
                slide_no=item.slide_no,
                media_refs=tuple(knowledge_media_ref_view(ref) for ref in item.media_refs),
            )
            for item in result.items
        ]

    async def get_agent_spaces(
        self, principal: PrincipalContext, tenant_id: str, agent_id: str
    ) -> AgentKnowledgeSpaceBindingsView:
        await self._require_agent_access(principal, tenant_id, agent_id, "agents.read")
        space_ids = await self.repository.agent_space_ids(tenant_id, agent_id)
        for space_id in space_ids:
            await self._accessible_space(principal, tenant_id, space_id, "knowledge.spaces.read")
        return AgentKnowledgeSpaceBindingsView(space_ids=space_ids)

    async def test_agent_search(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        agent_id: str,
        payload: AgentKnowledgeSearchTestRequest,
    ) -> AgentKnowledgeSearchTestView:
        await self._require_agent_access(principal, tenant_id, agent_id, "agents.read")
        await self._enter(principal, tenant_id, "knowledge.query")
        if self.settings is None or self.cipher is None:
            raise AppError(
                "KNOWLEDGE_RUNTIME_UNAVAILABLE",
                "Knowledge runtime is unavailable",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        from app.modules.knowledge.runtime import KnowledgeRuntimeContext, SqlKnowledgeRuntime

        result = await SqlKnowledgeRuntime(
            self.database,
            settings=self.settings,
            cipher=self.cipher,
            candidate_multiplier=self.settings.knowledge.vector.candidate_multiplier,
            reciprocal_rank_constant=self.settings.knowledge.vector.reciprocal_rank_constant,
        ).retrieve(
            KnowledgeRuntimeContext(
                tenant_id=tenant_id,
                agent_id=agent_id,
                query=payload.query,
                limit=payload.limit,
            )
        )
        return AgentKnowledgeSearchTestView(
            status=result.status,
            retrieval_method=result.retrieval_method,
            candidate_count=result.candidate_count,
            duration_ms=result.duration_ms,
            degradation_reasons=result.degradation_reasons,
            items=tuple(
                AgentKnowledgeSearchTestItem(
                    citation_id=item.citation_id,
                    title=item.title,
                    citation_anchor=item.citation_anchor,
                    space_id=item.space_id,
                    retrieval_method=item.retrieval_method,
                    score=item.score,
                    excerpt=item.excerpt,
                    embedding_config_name=item.embedding_config_name,
                    reranker_config_name=item.reranker_config_name,
                    degradation_reason=item.degradation_reason,
                    match_sources=item.match_sources,
                    vector_score=item.vector_score,
                    slide_no=item.slide_no,
                    media_refs=tuple(knowledge_media_ref_view(ref) for ref in item.media_refs),
                )
                for item in result.items
            ),
        )

    async def replace_agent_spaces(
        self, principal: PrincipalContext, tenant_id: str, agent_id: str, space_ids: tuple[str, ...]
    ) -> AgentKnowledgeSpaceBindingsView:
        await self._require_agent_access(principal, tenant_id, agent_id, "agents.manage")
        unique_ids = tuple(dict.fromkeys(space_ids))
        current_ids = await self.repository.agent_space_ids(tenant_id, agent_id)
        for space_id in tuple(dict.fromkeys((*current_ids, *unique_ids))):
            await self._accessible_space(principal, tenant_id, space_id, "knowledge.spaces.read")
        await self.repository.replace_agent_spaces(tenant_id, agent_id, unique_ids)
        await self.session.flush()
        append_audit(
            self.session,
            principal,
            "agent.knowledge_spaces.replace",
            "agent",
            agent_id,
            {"space_ids": unique_ids},
            tenant_id=tenant_id,
        )
        return AgentKnowledgeSpaceBindingsView(space_ids=unique_ids)

    async def get_space_agents(
        self, principal: PrincipalContext, tenant_id: str, space_id: str
    ) -> KnowledgeSpaceAgentBindingsView:
        await self._enter(principal, tenant_id, "agents.read")
        await self._accessible_space(principal, tenant_id, space_id, "knowledge.spaces.read")
        return KnowledgeSpaceAgentBindingsView(
            agent_ids=await self.repository.space_agent_ids(tenant_id, space_id)
        )

    async def add_agent_space(
        self, principal: PrincipalContext, tenant_id: str, agent_id: str, space_id: str
    ) -> AgentKnowledgeSpaceBindingsView:
        await self._require_agent_access(principal, tenant_id, agent_id, "agents.manage")
        await self._accessible_space(principal, tenant_id, space_id, "knowledge.spaces.read")
        created = await self.repository.add_agent_space(tenant_id, agent_id, space_id)
        space_ids = await self.repository.agent_space_ids(tenant_id, agent_id)
        if created:
            append_audit(
                self.session,
                principal,
                "agent.knowledge_spaces.add",
                "agent",
                agent_id,
                {"space_id": space_id},
                tenant_id=tenant_id,
            )
        return AgentKnowledgeSpaceBindingsView(space_ids=space_ids)

    async def remove_agent_space(
        self, principal: PrincipalContext, tenant_id: str, agent_id: str, space_id: str
    ) -> AgentKnowledgeSpaceBindingsView:
        await self._require_agent_access(principal, tenant_id, agent_id, "agents.manage")
        await self._accessible_space(principal, tenant_id, space_id, "knowledge.spaces.read")
        removed = await self.repository.remove_agent_space(tenant_id, agent_id, space_id)
        space_ids = await self.repository.agent_space_ids(tenant_id, agent_id)
        if removed:
            append_audit(
                self.session,
                principal,
                "agent.knowledge_spaces.remove",
                "agent",
                agent_id,
                {"space_id": space_id},
                tenant_id=tenant_id,
            )
        return AgentKnowledgeSpaceBindingsView(space_ids=space_ids)

    async def _accessible_space(
        self, principal: PrincipalContext, tenant_id: str, space_id: str, permission: str
    ) -> KnowledgeSpace:
        return await self.access_policy.require_space(
            principal, tenant_id, space_id, permission, self.repository
        )

    async def _require_agent_access(
        self, principal: PrincipalContext, tenant_id: str, agent_id: str, permission: str
    ) -> None:
        await self._enter(principal, tenant_id, permission)
        if not await self.agents.exists(tenant_id, agent_id):
            raise AppError("RESOURCE_NOT_FOUND", "Agent not found", status.HTTP_404_NOT_FOUND)

    async def _validate_retrieval_configs(
        self,
        tenant_id: str,
        payload: KnowledgeSpaceCreateRequest | KnowledgeSpaceRetrievalUpdateRequest,
        *,
        allow_disabled_embedding: bool = False,
    ) -> EmbeddingConfig | None:
        return await validate_retrieval_configs(
            self.session,
            self.settings,
            tenant_id,
            payload,
            allow_disabled_embedding=allow_disabled_embedding,
        )

    async def _enter(self, principal: PrincipalContext, tenant_id: str, permission: str) -> None:
        await self.access_policy.enter(principal, tenant_id, permission)

    async def _ensure_available_title(self, tenant_id: str, space_id: str, title_key: str) -> None:
        if await self.repository.available_document_exists(tenant_id, space_id, title_key):
            raise available_title_error()
