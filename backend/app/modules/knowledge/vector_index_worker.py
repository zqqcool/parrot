from __future__ import annotations

import hashlib
import logging
import os
import socket
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import SYSTEM_CLOCK, Clock
from app.core.config import AppConfig
from app.core.ids import new_id
from app.core.task_dispatch import TaskDispatcher
from app.infrastructure.credential_cipher import CredentialCipher
from app.infrastructure.db.session import DatabaseManager
from app.modules.embedding_configs.models import EmbeddingConfig
from app.modules.knowledge import runtime_helpers
from app.modules.knowledge.embedding import KnowledgeEmbeddingPort
from app.modules.knowledge.models import (
    KnowledgeChunk,
    KnowledgeDocumentVersion,
    KnowledgeVectorIndexJob,
    KnowledgeVectorReference,
)
from app.modules.knowledge.retrieval_clients import ConfiguredKnowledgeEmbedding
from app.modules.knowledge.vector_jobs import (
    enqueue_vector_job,
    knowledge_space_index_status,
    knowledge_space_index_statuses_statement,
    knowledge_space_index_target_statement,
)
from app.modules.knowledge.vector_store import KnowledgeVector, KnowledgeVectorStore
from app.modules.tenancy.models import Tenant

logger = logging.getLogger(__name__)
MAX_INDEX_ATTEMPTS = 5
_VECTOR_INDEX_LEASE_DURATION = timedelta(minutes=10)


@dataclass(frozen=True)
class ClaimedKnowledgeVectorJob:
    id: str
    tenant_id: str
    document_version_id: str
    embedding_config_id: str | None
    index_revision: int
    action: str


class KnowledgeVectorIndexWorker:
    """TaskIQ-invoked knowledge-vector operation processor."""

    def __init__(
        self,
        settings: AppConfig,
        embeddings: KnowledgeEmbeddingPort | None = None,
        vectors: KnowledgeVectorStore | None = None,
        *,
        cipher: CredentialCipher | None = None,
        dispatcher: TaskDispatcher | None = None,
        clock: Clock = SYSTEM_CLOCK,
    ) -> None:
        self._settings = settings
        self._database = DatabaseManager(settings.database)
        self._embeddings = embeddings
        self._vectors = vectors
        self._cipher = cipher
        self._dispatcher = dispatcher
        self._clock = clock
        self._owner = f"{socket.gethostname()}:{os.getpid()}:taskiq-knowledge-vector"

    async def close(self) -> None:
        await self._database.dispose()

    async def process(self, tenant_id: str, job_id: str) -> bool:
        claim = await self._claim(tenant_id, job_id)
        if claim is None:
            return False
        await self._process(claim)
        return True

    async def backfill(self) -> int:
        total = 0
        for tenant_id in await self._tenant_ids():
            async with self._database.session() as session:
                await self._database.set_tenant(session, tenant_id)
                version_ids = await session.scalars(
                    select(KnowledgeDocumentVersion.id).where(
                        KnowledgeDocumentVersion.tenant_id == tenant_id,
                        KnowledgeDocumentVersion.status == "published",
                    )
                )
                for version_id in version_ids:
                    if await enqueue_vector_job(
                        session,
                        tenant_id,
                        version_id,
                        "upsert",
                        dispatcher=self._dispatcher,
                    ):
                        total += 1
        return total

    async def _tenant_ids(self) -> tuple[str, ...]:
        async with self._database.platform_session() as session:
            rows = await session.scalars(select(Tenant.id).where(Tenant.status == "active"))
            return tuple(rows)

    async def _claim(self, tenant_id: str, job_id: str) -> ClaimedKnowledgeVectorJob | None:
        now = self._clock.now()
        async with self._database.session() as session:
            await self._database.set_tenant(session, tenant_id)
            job = await session.scalar(
                select(KnowledgeVectorIndexJob)
                .where(
                    KnowledgeVectorIndexJob.tenant_id == tenant_id,
                    KnowledgeVectorIndexJob.id == job_id,
                    KnowledgeVectorIndexJob.status.in_(("queued", "running")),
                    or_(
                        KnowledgeVectorIndexJob.lease_until.is_(None),
                        KnowledgeVectorIndexJob.lease_until < now,
                    ),
                )
                .order_by(KnowledgeVectorIndexJob.created_at)
                .with_for_update(skip_locked=True)
            )
            if job is None:
                return None
            job.status = "running"
            job.attempts += 1
            job.lease_owner = self._owner
            job.lease_until = now + _VECTOR_INDEX_LEASE_DURATION
            return ClaimedKnowledgeVectorJob(
                id=job.id,
                tenant_id=job.tenant_id,
                document_version_id=job.document_version_id,
                embedding_config_id=job.embedding_config_id,
                index_revision=job.index_revision,
                action=job.action,
            )

    async def _process(self, claim: ClaimedKnowledgeVectorJob) -> None:
        logger.info(
            "Knowledge index job started",
            extra={
                "tenant_id": claim.tenant_id,
                "document_version_id": claim.document_version_id,
                "job_id": claim.id,
            },
        )
        try:
            version, chunks, references, profile = await self._state(claim)
            if version is None or claim.action == "delete" or version.status != "published":
                await self._delete_vectors(references, profile)
                await self._replace_references(claim, ())
            else:
                if profile is None:
                    raise ValueError("Knowledge embedding config is unavailable")
                vectors = await self._build_vectors(version, chunks, profile)
                await self._delete_vectors(references, profile)
                await self._vector_store(profile).upsert(vectors)
                await self._replace_references(claim, vectors)
            await self._set_job(claim, "succeeded", None)
            logger.info(
                "Knowledge index job completed",
                extra={
                    "tenant_id": claim.tenant_id,
                    "document_version_id": claim.document_version_id,
                    "job_id": claim.id,
                },
            )
        except Exception:
            logger.exception(
                "Knowledge vector indexing failed",
                extra={
                    "tenant_id": claim.tenant_id,
                    "document_version_id": claim.document_version_id,
                },
            )
            await self._retry_or_fail(claim, "KNOWLEDGE_VECTOR_INDEX_FAILED")

    async def _state(
        self, claim: ClaimedKnowledgeVectorJob
    ) -> tuple[
        KnowledgeDocumentVersion | None,
        tuple[KnowledgeChunk, ...],
        tuple[KnowledgeVectorReference, ...],
        EmbeddingConfig | None,
    ]:
        async with self._database.session() as session:
            await self._database.set_tenant(session, claim.tenant_id)
            version = await session.scalar(
                select(KnowledgeDocumentVersion).where(
                    KnowledgeDocumentVersion.tenant_id == claim.tenant_id,
                    KnowledgeDocumentVersion.id == claim.document_version_id,
                )
            )
            chunks = await session.scalars(
                select(KnowledgeChunk)
                .where(
                    KnowledgeChunk.tenant_id == claim.tenant_id,
                    KnowledgeChunk.document_version_id == claim.document_version_id,
                )
                .order_by(KnowledgeChunk.ordinal)
            )
            references = await session.scalars(
                select(KnowledgeVectorReference).where(
                    KnowledgeVectorReference.tenant_id == claim.tenant_id,
                    KnowledgeVectorReference.document_version_id == claim.document_version_id,
                    KnowledgeVectorReference.embedding_config_id == claim.embedding_config_id,
                    KnowledgeVectorReference.index_revision == claim.index_revision,
                )
            )
            profile = (
                await session.scalar(
                    select(EmbeddingConfig).where(
                        EmbeddingConfig.tenant_id == claim.tenant_id,
                        EmbeddingConfig.id == claim.embedding_config_id,
                    )
                )
                if claim.embedding_config_id is not None
                else None
            )
            return version, tuple(chunks), tuple(references), profile

    async def _build_vectors(
        self,
        version: KnowledgeDocumentVersion,
        chunks: tuple[KnowledgeChunk, ...],
        profile: EmbeddingConfig | None = None,
    ) -> tuple[KnowledgeVector, ...]:
        values = tuple(chunk.content for chunk in chunks)
        embeddings = await self._embedding_client(profile).embed(values)
        if len(embeddings) != len(chunks):
            raise ValueError("Knowledge embedding service returned an incomplete chunk set")
        identity = profile.id if profile is not None else self._settings.knowledge.embedding.model
        model_digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
        return tuple(
            KnowledgeVector(
                id=f"{chunk.id}:e{model_digest}",
                tenant_id=chunk.tenant_id,
                space_id=chunk.space_id,
                document_version_id=version.id,
                chunk_id=chunk.id,
                vector=embedding,
            )
            for chunk, embedding in zip(chunks, embeddings, strict=True)
        )

    async def _delete_vectors(
        self, references: tuple[KnowledgeVectorReference, ...], profile: EmbeddingConfig | None
    ) -> None:
        if not references:
            return
        await self._vector_store(profile).delete(tuple(item.vector_id for item in references))

    async def _replace_references(
        self,
        claim: ClaimedKnowledgeVectorJob,
        vectors: tuple[KnowledgeVector, ...],
    ) -> None:
        async with self._database.session() as session:
            await self._database.set_tenant(session, claim.tenant_id)
            await session.execute(
                delete(KnowledgeVectorReference).where(
                    KnowledgeVectorReference.tenant_id == claim.tenant_id,
                    KnowledgeVectorReference.document_version_id == claim.document_version_id,
                    KnowledgeVectorReference.embedding_config_id == claim.embedding_config_id,
                    KnowledgeVectorReference.index_revision == claim.index_revision,
                )
            )
            session.add_all(
                KnowledgeVectorReference(
                    id=new_id("knowledge_vector"),
                    tenant_id=claim.tenant_id,
                    document_version_id=claim.document_version_id,
                    chunk_id=vector.chunk_id,
                    vector_id=vector.id,
                    collection=self._collection(profile_id=claim.embedding_config_id),
                    embedding_model=claim.embedding_config_id
                    or self._settings.knowledge.embedding.model,
                    embedding_config_id=claim.embedding_config_id,
                    index_revision=claim.index_revision,
                )
                for vector in vectors
            )

    async def _set_job(
        self, claim: ClaimedKnowledgeVectorJob, status: str, error_code: str | None
    ) -> None:
        async with self._database.session() as session:
            await self._database.set_tenant(session, claim.tenant_id)
            job = await session.scalar(
                select(KnowledgeVectorIndexJob).where(
                    KnowledgeVectorIndexJob.tenant_id == claim.tenant_id,
                    KnowledgeVectorIndexJob.id == claim.id,
                    KnowledgeVectorIndexJob.lease_owner == self._owner,
                )
            )
            if job is not None:
                job.status = status
                job.error_code = error_code
                job.lease_owner = None
                job.lease_until = None
                await session.flush()
                await self._refresh_index_status(session, claim)

    async def _retry_or_fail(self, claim: ClaimedKnowledgeVectorJob, error_code: str) -> None:
        delay_seconds = 0
        async with self._database.session() as session:
            await self._database.set_tenant(session, claim.tenant_id)
            job = await session.scalar(
                select(KnowledgeVectorIndexJob).where(
                    KnowledgeVectorIndexJob.tenant_id == claim.tenant_id,
                    KnowledgeVectorIndexJob.id == claim.id,
                    KnowledgeVectorIndexJob.lease_owner == self._owner,
                )
            )
            if job is None:
                return
            retry = job.attempts < MAX_INDEX_ATTEMPTS
            job.status = "queued" if retry else "failed"
            job.error_code = error_code
            job.lease_owner = None
            job.lease_until = (
                self._clock.now() + timedelta(seconds=min(2**job.attempts, 60)) if retry else None
            )
            delay_seconds = min(2**job.attempts, 60) if retry else 0
            await session.flush()
            await self._refresh_index_status(session, claim)
        if delay_seconds and self._dispatcher is not None:
            await self._dispatcher.dispatch_knowledge_vector(
                claim.tenant_id, claim.id, delay_seconds=delay_seconds
            )

    def _embedding_client(self, profile: EmbeddingConfig | None) -> KnowledgeEmbeddingPort:
        if profile is not None and self._cipher is not None:
            return ConfiguredKnowledgeEmbedding(self._settings, self._cipher, profile)
        if self._embeddings is None:
            raise ValueError("Knowledge embedding client is unavailable")
        return self._embeddings

    def _vector_store(self, profile: EmbeddingConfig | None) -> KnowledgeVectorStore:
        if profile is not None:
            from app.modules.knowledge.vector_store import MilvusKnowledgeVectorStore

            return MilvusKnowledgeVectorStore(
                self._settings,
                collection=self._collection(profile_id=profile.id),
                embedding_dimension=profile.embedding_dimension,
            )
        if self._vectors is None:
            raise ValueError("Knowledge vector store is unavailable")
        return self._vectors

    def _collection(self, *, profile_id: str | None) -> str:
        if profile_id is None:
            return self._settings.knowledge.vector.collection
        return runtime_helpers.collection_name(self._settings, profile_id)

    async def _refresh_index_status(
        self, session: AsyncSession, claim: ClaimedKnowledgeVectorJob
    ) -> None:
        if claim.embedding_config_id is None:
            return
        space = await session.scalar(
            knowledge_space_index_target_statement(
                tenant_id=claim.tenant_id,
                document_version_id=claim.document_version_id,
                embedding_config_id=claim.embedding_config_id,
                index_revision=claim.index_revision,
            )
        )
        if space is None:
            return
        statuses = await session.scalars(
            knowledge_space_index_statuses_statement(
                tenant_id=claim.tenant_id,
                space_id=space.id,
                embedding_config_id=claim.embedding_config_id,
                index_revision=claim.index_revision,
            )
        )
        space.retrieval_index_status = knowledge_space_index_status(statuses)
