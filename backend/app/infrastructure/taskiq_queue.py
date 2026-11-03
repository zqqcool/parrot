from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any

from taskiq import ScheduleSource, TaskiqScheduler
from taskiq.serializers import JSONSerializer
from taskiq_redis import ListRedisScheduleSource, RedisStreamBroker

from app.core.config import AppConfig
from app.core.task_dispatch import TaskDispatcher

RecurringScheduleRegistrar = Callable[[], Awaitable[None]]


class ParrotTaskiqScheduler(TaskiqScheduler):
    """Register deployment-owned recurring work only in the scheduler process."""

    def __init__(
        self,
        broker: RedisStreamBroker,
        sources: list[ScheduleSource],
        register_recurring_schedules: RecurringScheduleRegistrar,
    ) -> None:
        super().__init__(broker, sources)
        self._register_recurring_schedules = register_recurring_schedules

    async def startup(self) -> None:
        await super().startup()
        await self._register_recurring_schedules()


class TaskiqQueue(TaskDispatcher):
    """TaskIQ producer and durable one-shot schedule registry.

    Runtime interactions are directly published after their accepted state is
    committed. Delayed background delivery uses the schedule registry; every
    handler reloads and validates its tenant-owned record before doing work.
    """

    def __init__(
        self,
        settings: AppConfig,
        broker: RedisStreamBroker,
        schedule_source: ListRedisScheduleSource,
        *,
        runtime: Any,
        memory_index: Any,
        knowledge_ingestion: Any,
        knowledge_staging_cleanup: Any,
        knowledge_vector: Any,
        capability_index: Any,
        skill_build: Any,
        scheduled_task: Any,
    ) -> None:
        self.settings = settings
        self.broker = broker
        self.schedule_source = schedule_source
        self._runtime = runtime
        self._memory_index = memory_index
        self._knowledge_ingestion = knowledge_ingestion
        self._knowledge_staging_cleanup = knowledge_staging_cleanup
        self._knowledge_vector = knowledge_vector
        self._capability_index = capability_index
        self._skill_build = skill_build
        self._scheduled_task = scheduled_task
        self.scheduler = ParrotTaskiqScheduler(
            broker,
            [schedule_source],
            self.register_recurring_schedules,
        )

    async def dispatch_runtime(self, tenant_id: str, interaction_id: str) -> None:
        await self._runtime.kiq(tenant_id, interaction_id)

    async def dispatch_memory_index(self, tenant_id: str, job_id: str) -> None:
        await self._schedule_delivery(self._memory_index, "memory-index", tenant_id, job_id)

    async def dispatch_knowledge_ingestion(self, tenant_id: str, job_id: str) -> None:
        await self._schedule_delivery(
            self._knowledge_ingestion, "knowledge-ingestion", tenant_id, job_id
        )

    async def dispatch_knowledge_vector(
        self, tenant_id: str, job_id: str, *, delay_seconds: int = 0
    ) -> None:
        await self._schedule_delivery(
            self._knowledge_vector,
            "knowledge-vector",
            tenant_id,
            job_id,
            delay_seconds=delay_seconds,
        )

    async def dispatch_capability_index(
        self,
        tenant_id: str,
        source_kind: str,
        source_id: str,
        source_revision: str,
        *,
        delay_seconds: int = 0,
        attempt: int = 0,
    ) -> None:
        if not self.settings.capability_index.enabled:
            return
        delay = self.settings.taskiq.dispatch_delay_seconds + delay_seconds
        execute_at = datetime.now(UTC) + timedelta(seconds=delay)
        identity = ":".join((tenant_id, source_kind, source_id, source_revision, str(attempt)))
        schedule_id = f"dispatch:capability-index:{sha256(identity.encode()).hexdigest()[:24]}"
        await self.schedule_source.delete_schedule(schedule_id)
        await (
            self._capability_index.kicker()
            .with_schedule_id(schedule_id)
            .schedule_by_time(
                self.schedule_source,
                execute_at,
                tenant_id,
                source_kind,
                source_id,
                source_revision,
                attempt,
            )
        )

    async def dispatch_skill_build(self, tenant_id: str, job_id: str) -> None:
        await self._schedule_delivery(self._skill_build, "skill-build", tenant_id, job_id)

    async def schedule_task(self, tenant_id: str, schedule_id: str, trigger_at: datetime) -> None:
        key = f"schedule:{schedule_id}"
        await self.schedule_source.delete_schedule(key)
        await (
            self._scheduled_task.kicker()
            .with_schedule_id(key)
            .schedule_by_time(
                self.schedule_source,
                _as_utc(trigger_at),
                tenant_id,
                schedule_id,
                _as_utc(trigger_at).isoformat(),
            )
        )

    async def remove_schedule(self, schedule_id: str) -> None:
        await self.schedule_source.delete_schedule(f"schedule:{schedule_id}")

    async def close(self) -> None:
        await self.broker.shutdown()

    async def register_recurring_schedules(self) -> None:
        schedule_id = "recurring:knowledge-staging-cleanup"
        await self.schedule_source.delete_schedule(schedule_id)
        await (
            self._knowledge_staging_cleanup.kicker()
            .with_schedule_id(schedule_id)
            .schedule_by_cron(self.schedule_source, "0 * * * *")
        )

    async def _schedule_delivery(
        self,
        task: Any,
        kind: str,
        tenant_id: str,
        resource_id: str,
        *,
        delay_seconds: int = 0,
    ) -> None:
        delay = self.settings.taskiq.dispatch_delay_seconds + delay_seconds
        execute_at = datetime.now(UTC) + timedelta(seconds=delay)
        schedule_id = f"dispatch:{kind}:{resource_id}"
        await self.schedule_source.delete_schedule(schedule_id)
        await (
            task.kicker()
            .with_schedule_id(schedule_id)
            .schedule_by_time(self.schedule_source, execute_at, tenant_id, resource_id)
        )


def create_broker(settings: AppConfig) -> RedisStreamBroker:
    if not settings.redis.enabled:
        raise ValueError("TaskIQ requires redis.enabled = true")
    return RedisStreamBroker(
        settings.redis.url,
        queue_name=settings.taskiq.queue_name,
        consumer_group_name=settings.taskiq.consumer_group,
        # A group created after deployment must also consume already queued work.
        consumer_id="0-0",
        maxlen=settings.taskiq.stream_maxlen,
        idle_timeout=settings.taskiq.unacknowledged_idle_seconds * 1000,
    )


def create_schedule_source(settings: AppConfig) -> ListRedisScheduleSource:
    return ListRedisScheduleSource(
        settings.redis.url,
        prefix=settings.taskiq.schedule_prefix,
        serializer=JSONSerializer(),
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("TaskIQ schedules must use timezone-aware datetimes")
    return value.astimezone(UTC)
