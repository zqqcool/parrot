from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import AppConfig
from app.core.task_dispatch import TaskDispatcher
from app.infrastructure.db.session import DatabaseManager
from app.infrastructure.redis import RedisManager
from app.modules.agents.catalog import AgentCatalog
from app.modules.interactions.runtime_factory import build_profile_resolver, build_runtime
from app.modules.schedules.service import ScheduleService


class ScheduleTaskProcessor:
    """Builds the tenant-scoped service used by one TaskIQ schedule delivery."""

    def __init__(self, settings: AppConfig, dispatcher: TaskDispatcher) -> None:
        self._settings = settings
        self._dispatcher = dispatcher
        self._database = DatabaseManager(settings.database)
        self._redis = RedisManager(settings.redis)

    async def process(
        self, tenant_id: str, schedule_id: str, expected_trigger_at: datetime
    ) -> bool:
        async with self._database.session() as session:
            return await self._service(session).execute_taskiq(
                tenant_id, schedule_id, expected_trigger_at
            )

    async def close(self) -> None:
        await self._redis.close()
        await self._database.dispose()

    def _service(self, session: AsyncSession) -> ScheduleService:
        return ScheduleService(
            session,
            self._database,
            build_runtime(self._settings, self._dispatcher),
            AgentCatalog(session),
            self._settings.schedules.default_timezone,
            self._redis,
            build_profile_resolver(self._settings, session),
            self._dispatcher,
        )
