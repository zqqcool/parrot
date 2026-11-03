from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import AppConfig
from app.infrastructure.credential_cipher import CredentialCipher
from app.infrastructure.db.session import DatabaseManager
from app.infrastructure.qiniu_object_storage import QiniuObjectStorage
from app.infrastructure.taskiq_queue import TaskiqQueue, create_broker, create_schedule_source
from app.modules.capability_index.worker import CapabilityIndexWorker
from app.modules.interactions.models import Interaction
from app.modules.interactions.runtime_factory import build_runtime_worker
from app.modules.knowledge.ingestion_worker import KnowledgeIngestionWorker
from app.modules.knowledge.models import KnowledgeIngestionJob, KnowledgeVectorIndexJob
from app.modules.knowledge.staging_cleanup_worker import KnowledgeStagingCleanupWorker
from app.modules.knowledge.vector_index_worker import KnowledgeVectorIndexWorker
from app.modules.mcp_servers.models import McpServer
from app.modules.memory.embedding import OpenAiCompatibleEmbeddingClient
from app.modules.memory.index_worker import MemoryIndexWorker
from app.modules.memory.models import MemoryIndexJob
from app.modules.memory.vector_store import MilvusMemoryVectorStore
from app.modules.schedules.models import ScheduledTask
from app.modules.schedules.worker import ScheduleTaskProcessor
from app.modules.skills.build_service import SkillBuildWorker
from app.modules.skills.models import Skill, SkillBuildJob
from app.modules.tenancy.models import Tenant

logger = logging.getLogger(__name__)
MAX_CAPABILITY_INDEX_ATTEMPTS = 3


class TaskiqRuntime:
    """The only composition root for Parrot background execution."""

    def __init__(self, settings: AppConfig) -> None:
        self.settings = settings
        broker = create_broker(settings)
        source = create_schedule_source(settings)

        @broker.task(task_name="parrot.runtime.execute")
        async def runtime_task(tenant_id: str, interaction_id: str) -> bool:
            worker = build_runtime_worker(settings, self.queue)
            try:
                return await worker.process(tenant_id, interaction_id)
            finally:
                await worker.close()

        @broker.task(task_name="parrot.memory.index")
        async def memory_index_task(tenant_id: str, job_id: str) -> bool:
            embeddings = None
            if settings.memory.vector.enabled:
                embeddings = OpenAiCompatibleEmbeddingClient(settings)
            vectors = MilvusMemoryVectorStore(settings) if settings.memory.vector.enabled else None
            worker = MemoryIndexWorker(settings, embeddings, vectors, dispatcher=self.queue)
            try:
                return await worker.process(tenant_id, job_id)
            finally:
                await worker.close()

        @broker.task(task_name="parrot.knowledge.ingest")
        async def knowledge_ingestion_task(tenant_id: str, job_id: str) -> bool:
            worker = KnowledgeIngestionWorker(
                settings,
                QiniuObjectStorage(settings.object_storage),
                dispatcher=self.queue,
            )
            try:
                return await worker.process(tenant_id, job_id)
            finally:
                await worker.close()

        @broker.task(task_name="parrot.knowledge.staging-cleanup")
        async def knowledge_staging_cleanup_task() -> int:
            worker = KnowledgeStagingCleanupWorker(
                settings,
                QiniuObjectStorage(settings.object_storage),
            )
            try:
                return await worker.process()
            finally:
                await worker.close()

        @broker.task(task_name="parrot.knowledge.vector-index")
        async def knowledge_vector_task(tenant_id: str, job_id: str) -> bool:
            worker = KnowledgeVectorIndexWorker(
                settings,
                cipher=CredentialCipher(
                    settings.security.credential_encryption_key.get_secret_value()
                ),
                dispatcher=self.queue,
            )
            try:
                return await worker.process(tenant_id, job_id)
            finally:
                await worker.close()

        @broker.task(task_name="parrot.capability.index")
        async def capability_index_task(
            tenant_id: str,
            source_kind: str,
            source_id: str,
            source_revision: str,
            attempt: int = 0,
        ) -> bool:
            return await self._process_capability_index(
                tenant_id, source_kind, source_id, source_revision, attempt
            )

        @broker.task(task_name="parrot.skills.build")
        async def skill_build_task(tenant_id: str, job_id: str) -> bool:
            worker = SkillBuildWorker(settings)
            try:
                return await worker.process(tenant_id, job_id)
            finally:
                await worker.close()

        @broker.task(task_name="parrot.schedules.execute")
        async def scheduled_task(
            tenant_id: str, schedule_id: str, expected_trigger_at: str
        ) -> bool:
            processor = ScheduleTaskProcessor(settings, self.queue)
            try:
                return await processor.process(
                    tenant_id, schedule_id, datetime.fromisoformat(expected_trigger_at)
                )
            finally:
                await processor.close()

        self.queue = TaskiqQueue(
            settings,
            broker,
            source,
            runtime=runtime_task,
            memory_index=memory_index_task,
            knowledge_ingestion=knowledge_ingestion_task,
            knowledge_staging_cleanup=knowledge_staging_cleanup_task,
            knowledge_vector=knowledge_vector_task,
            capability_index=capability_index_task,
            skill_build=skill_build_task,
            scheduled_task=scheduled_task,
        )

    async def close(self) -> None:
        await self.queue.close()

    async def _process_capability_index(
        self,
        tenant_id: str,
        source_kind: str,
        source_id: str,
        source_revision: str,
        attempt: int,
    ) -> bool:
        if not self.settings.capability_index.enabled:
            return False
        worker = CapabilityIndexWorker(
            self.settings,
            cipher=CredentialCipher(
                self.settings.security.credential_encryption_key.get_secret_value()
            ),
        )
        try:
            return await worker.process(tenant_id, source_kind, source_id, source_revision)
        except Exception:
            logger.exception(
                "Capability indexing task failed",
                extra={
                    "tenant_id": tenant_id,
                    "source_kind": source_kind,
                    "source_id": source_id,
                },
            )
            if attempt + 1 < MAX_CAPABILITY_INDEX_ATTEMPTS:
                await self.queue.dispatch_capability_index(
                    tenant_id,
                    source_kind,
                    source_id,
                    source_revision,
                    delay_seconds=2**attempt,
                    attempt=attempt + 1,
                )
            return False
        finally:
            await worker.close()


async def backfill_taskiq_delivery(settings: AppConfig) -> dict[str, int]:
    """One-time migration helper for records created before TaskIQ was enabled."""
    runtime = TaskiqRuntime(settings)
    database = DatabaseManager(settings.database)
    totals = {
        "runtime": 0,
        "memory_index": 0,
        "knowledge_ingestion": 0,
        "knowledge_vector": 0,
        "capability_index": 0,
        "skill_build": 0,
        "schedules": 0,
    }
    try:
        async with database.platform_session() as session:
            tenant_ids = tuple(
                await session.scalars(select(Tenant.id).where(Tenant.status == "active"))
            )
        for tenant_id in tenant_ids:
            async with database.session() as session:
                await database.set_tenant(session, tenant_id)
                runtime_ids = tuple(
                    await session.scalars(
                        select(Interaction.id).where(
                            Interaction.tenant_id == tenant_id,
                            Interaction.status.in_(("accepted", "running")),
                            Interaction.runtime_execution_id.like("runtime:%"),
                        )
                    )
                )
                memory_ids = tuple(
                    await session.scalars(
                        select(MemoryIndexJob.id).where(
                            MemoryIndexJob.tenant_id == tenant_id,
                            MemoryIndexJob.status.in_(("queued", "running")),
                        )
                    )
                )
                ingestion_ids = tuple(
                    await session.scalars(
                        select(KnowledgeIngestionJob.id).where(
                            KnowledgeIngestionJob.tenant_id == tenant_id,
                            KnowledgeIngestionJob.status.in_(("queued", "running")),
                        )
                    )
                )
                vector_ids = tuple(
                    await session.scalars(
                        select(KnowledgeVectorIndexJob.id).where(
                            KnowledgeVectorIndexJob.tenant_id == tenant_id,
                            KnowledgeVectorIndexJob.status.in_(("queued", "running")),
                        )
                    )
                )
                build_ids = tuple(
                    await session.scalars(
                        select(SkillBuildJob.id).where(
                            SkillBuildJob.tenant_id == tenant_id,
                            SkillBuildJob.status.in_(("queued", "running")),
                        )
                    )
                )
                skills, mcp_servers = await _capability_sources(session, tenant_id)
                schedules = tuple(
                    await session.scalars(
                        select(ScheduledTask).where(
                            ScheduledTask.tenant_id == tenant_id,
                            ScheduledTask.status == "enabled",
                            ScheduledTask.next_trigger_at.is_not(None),
                        )
                    )
                )
            for item_id in runtime_ids:
                await runtime.queue.dispatch_runtime(tenant_id, item_id)
            for job_id in memory_ids:
                await runtime.queue.dispatch_memory_index(tenant_id, job_id)
            for job_id in ingestion_ids:
                await runtime.queue.dispatch_knowledge_ingestion(tenant_id, job_id)
            for job_id in vector_ids:
                await runtime.queue.dispatch_knowledge_vector(tenant_id, job_id)
            for job_id in build_ids:
                await runtime.queue.dispatch_skill_build(tenant_id, job_id)
            await _dispatch_capability_backfill(runtime, tenant_id, skills, mcp_servers)
            for schedule in schedules:
                if schedule.next_trigger_at is not None:
                    await runtime.queue.schedule_task(
                        tenant_id, schedule.id, schedule.next_trigger_at
                    )
            totals["runtime"] += len(runtime_ids)
            totals["memory_index"] += len(memory_ids)
            totals["knowledge_ingestion"] += len(ingestion_ids)
            totals["knowledge_vector"] += len(vector_ids)
            totals["skill_build"] += len(build_ids)
            if settings.capability_index.enabled:
                totals["capability_index"] += len(skills) + len(mcp_servers)
            totals["schedules"] += len(schedules)
        return totals
    finally:
        await database.dispose()
        await runtime.close()


async def _capability_sources(
    session: AsyncSession, tenant_id: str
) -> tuple[tuple[Skill, ...], tuple[McpServer, ...]]:
    skills = tuple(
        await session.scalars(
            select(Skill).where(Skill.tenant_id == tenant_id, Skill.status == "published")
        )
    )
    servers = tuple(
        await session.scalars(
            select(McpServer).where(McpServer.tenant_id == tenant_id, McpServer.status == "active")
        )
    )
    return skills, servers


async def _dispatch_capability_backfill(
    runtime: TaskiqRuntime,
    tenant_id: str,
    skills: tuple[Skill, ...],
    servers: tuple[McpServer, ...],
) -> None:
    if not runtime.settings.capability_index.enabled:
        return
    for skill in skills:
        await runtime.queue.dispatch_capability_index(
            tenant_id, "skill", skill.id, str(skill.version)
        )
    for server in servers:
        await runtime.queue.dispatch_capability_index(
            tenant_id, "mcp_server", server.id, server.updated_at.isoformat()
        )
