from __future__ import annotations

import logging
import os
import socket
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import delete, or_, select
from sqlalchemy.dialects.postgresql import insert

from app.core.clock import SYSTEM_CLOCK, Clock
from app.core.config import AppConfig
from app.core.ids import new_id
from app.core.task_dispatch import TaskDispatcher
from app.infrastructure.db.session import DatabaseManager
from app.modules.memory.embedding import OpenAiCompatibleEmbeddingClient
from app.modules.memory.models import MemoryIndexJob, MemoryRecord, MemoryVectorReference
from app.modules.memory.vector_store import MemoryVector, MemoryVectorStore
from app.modules.tenancy.models import Tenant

logger = logging.getLogger(__name__)
_MEMORY_INDEX_LEASE_DURATION = timedelta(minutes=5)


@dataclass(frozen=True)
class ClaimedMemoryIndexJob:
    id: str
    tenant_id: str
    memory_id: str
    memory_version: int
    action: str


class MemoryIndexWorker:
    """TaskIQ-invoked vector operation processor."""

    def __init__(
        self,
        settings: AppConfig,
        embeddings: OpenAiCompatibleEmbeddingClient | None,
        vectors: MemoryVectorStore | None,
        *,
        dispatcher: TaskDispatcher | None = None,
        clock: Clock = SYSTEM_CLOCK,
    ) -> None:
        self._settings = settings
        self._database = DatabaseManager(settings.database)
        self._embeddings = embeddings
        self._vectors = vectors
        self._clock = clock
        self._dispatcher = dispatcher
        self._owner = f"{socket.gethostname()}:{os.getpid()}:taskiq-memory-index"

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
                rows = await session.scalars(
                    select(MemoryRecord).where(MemoryRecord.status == "active")
                )
                for memory in rows:
                    result = await session.execute(
                        insert(MemoryIndexJob)
                        .values(
                            id=new_id("memory_index"),
                            tenant_id=tenant_id,
                            memory_id=memory.id,
                            memory_version=memory.version,
                            action="index",
                        )
                        .on_conflict_do_nothing(constraint="uq_memory_index_job_version")
                        .returning(MemoryIndexJob.id)
                    )
                    job_id = result.scalar_one_or_none()
                    if job_id is not None:
                        total += 1
                        if self._dispatcher is not None:
                            await self._dispatcher.dispatch_memory_index(tenant_id, job_id)
        return total

    async def _tenant_ids(self) -> tuple[str, ...]:
        """One-off migration backfill only; it is never a queue consumer."""
        async with self._database.platform_session() as session:
            rows = await session.scalars(select(Tenant.id).where(Tenant.status == "active"))
            return tuple(rows)

    async def _claim(self, tenant_id: str, job_id: str) -> ClaimedMemoryIndexJob | None:
        now = self._clock.now()
        async with self._database.session() as session:
            await self._database.set_tenant(session, tenant_id)
            job = await session.scalar(
                select(MemoryIndexJob)
                .where(
                    MemoryIndexJob.tenant_id == tenant_id,
                    MemoryIndexJob.id == job_id,
                    MemoryIndexJob.status.in_(("queued", "running")),
                    or_(MemoryIndexJob.lease_until.is_(None), MemoryIndexJob.lease_until < now),
                )
                .order_by(MemoryIndexJob.created_at)
                .with_for_update(skip_locked=True)
            )
            if job is None:
                return None
            job.status = "running"
            job.lease_owner = self._owner
            job.lease_until = now + _MEMORY_INDEX_LEASE_DURATION
            await session.flush()
            return ClaimedMemoryIndexJob(
                id=job.id,
                tenant_id=job.tenant_id,
                memory_id=job.memory_id,
                memory_version=job.memory_version,
                action=job.action,
            )

    async def _process(self, claim: ClaimedMemoryIndexJob) -> None:
        logger.info(
            "Memory index job started",
            extra={"tenant_id": claim.tenant_id, "memory_id": claim.memory_id, "job_id": claim.id},
        )
        try:
            memory, references = await self._state(claim)
            if memory is None or memory.version != claim.memory_version:
                await self._complete(claim)
                return
            if self._must_delete(claim, memory):
                await self._delete_vectors(references)
                await self._replace_references(claim, ())
            elif self._embeddings is not None and self._vectors is not None:
                vectors = await self._build_vectors(memory)
                await self._vectors.upsert(vectors)
                await self._delete_vectors(references)
                await self._replace_references(claim, vectors)
            await self._complete(claim)
            logger.info(
                "Memory index job completed",
                extra={
                    "tenant_id": claim.tenant_id,
                    "memory_id": claim.memory_id,
                    "job_id": claim.id,
                },
            )
        except Exception:
            logger.exception(
                "Memory vector indexing failed",
                extra={"tenant_id": claim.tenant_id, "memory_id": claim.memory_id},
            )
            await self._fail(claim, "MEMORY_VECTOR_INDEX_FAILED")

    async def _state(
        self, claim: ClaimedMemoryIndexJob
    ) -> tuple[MemoryRecord | None, tuple[MemoryVectorReference, ...]]:
        async with self._database.session() as session:
            await self._database.set_tenant(session, claim.tenant_id)
            memory = await session.scalar(
                select(MemoryRecord).where(
                    MemoryRecord.tenant_id == claim.tenant_id,
                    MemoryRecord.id == claim.memory_id,
                )
            )
            references = await session.scalars(
                select(MemoryVectorReference).where(
                    MemoryVectorReference.tenant_id == claim.tenant_id,
                    MemoryVectorReference.memory_id == claim.memory_id,
                )
            )
            return memory, tuple(references)

    async def _build_vectors(self, memory: MemoryRecord) -> tuple[MemoryVector, ...]:
        if self._embeddings is None:
            return ()
        chunks = _chunks(memory.content)
        embeddings = await self._embeddings.embed(chunks)
        if len(embeddings) != len(chunks):
            raise ValueError("Embedding service returned an incomplete chunk set")
        return tuple(
            MemoryVector(
                id=f"{memory.id}:v{memory.version}:c{index}",
                memory_id=memory.id,
                chunk_index=index,
                vector=embedding,
                tenant_id=memory.tenant_id,
                agent_id=memory.agent_id,
                scope_type=memory.scope_type,
                scope_id=memory.scope_id,
            )
            for index, embedding in enumerate(embeddings)
        )

    async def _delete_vectors(self, references: tuple[MemoryVectorReference, ...]) -> None:
        if self._vectors is not None:
            await self._vectors.delete(tuple(item.vector_id for item in references))

    async def _replace_references(
        self, claim: ClaimedMemoryIndexJob, vectors: tuple[MemoryVector, ...]
    ) -> None:
        async with self._database.session() as session:
            await self._database.set_tenant(session, claim.tenant_id)
            await session.execute(
                delete(MemoryVectorReference).where(
                    MemoryVectorReference.tenant_id == claim.tenant_id,
                    MemoryVectorReference.memory_id == claim.memory_id,
                )
            )
            if self._vectors is not None:
                session.add_all(
                    MemoryVectorReference(
                        id=new_id("memory_vector"),
                        tenant_id=claim.tenant_id,
                        memory_id=claim.memory_id,
                        memory_version=claim.memory_version,
                        vector_id=vector.id,
                        chunk_index=vector.chunk_index,
                        collection=self._settings.memory.vector.collection,
                    )
                    for vector in vectors
                )

    async def _complete(self, claim: ClaimedMemoryIndexJob) -> None:
        await self._set_job(claim, "succeeded", None)

    async def _fail(self, claim: ClaimedMemoryIndexJob, code: str) -> None:
        await self._set_job(claim, "failed", code)

    async def _set_job(
        self, claim: ClaimedMemoryIndexJob, status: str, error_code: str | None
    ) -> None:
        async with self._database.session() as session:
            await self._database.set_tenant(session, claim.tenant_id)
            job = await session.scalar(
                select(MemoryIndexJob).where(
                    MemoryIndexJob.tenant_id == claim.tenant_id,
                    MemoryIndexJob.id == claim.id,
                    MemoryIndexJob.lease_owner == self._owner,
                )
            )
            if job is not None:
                job.status = status
                job.error_code = error_code
                job.lease_owner = None
                job.lease_until = None

    def _must_delete(self, claim: ClaimedMemoryIndexJob, memory: MemoryRecord) -> bool:
        return (
            claim.action == "delete"
            or memory.status != "active"
            or memory.requires_confirmation
            or (memory.expires_at is not None and memory.expires_at <= self._clock.now())
        )


def _chunks(value: str, size: int = 1_800) -> tuple[str, ...]:
    chunks = tuple(value[index : index + size] for index in range(0, len(value), size))
    return chunks or ("",)
