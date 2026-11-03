from __future__ import annotations

from app.core.config import AppConfig
from app.core.errors import AppError
from app.infrastructure.db.session import DatabaseManager
from app.infrastructure.redis import RedisManager
from app.modules.dashboard.repository import DashboardRepository
from app.modules.dashboard.schemas import (
    DashboardMetric,
    DashboardOverview,
    DashboardServiceStatus,
)
from app.modules.iam.schemas import PrincipalContext


class DashboardService:
    def __init__(
        self,
        repository: DashboardRepository,
        database: DatabaseManager,
        redis: RedisManager,
        settings: AppConfig,
    ) -> None:
        self.repository = repository
        self.database = database
        self.redis = redis
        self.settings = settings

    async def overview(self, principal: PrincipalContext, tenant_id: str) -> DashboardOverview:
        if principal.tenant_id != tenant_id:
            raise AppError("TENANT_NOT_FOUND", "Tenant not found", 404)
        await self.database.set_tenant(self.repository.session, tenant_id)
        agents = await self.repository.count_agents(tenant_id)
        llm_configs, skills, mcp_servers = await self.repository.count_capability_configs(tenant_id)
        im_entries = await self.repository.count_im_entries(tenant_id)
        runs, active_runs = await self.repository.count_runs(tenant_id)
        database_ok = await self.database.ping()
        redis_ok = await self.redis.ping()
        warnings = tuple(
            name for name, ready in (("PostgreSQL", database_ok), ("Redis", redis_ok)) if not ready
        )
        return DashboardOverview(
            agents=DashboardMetric(value=agents),
            llm_configs=DashboardMetric(value=llm_configs),
            skills=DashboardMetric(value=skills),
            mcp_servers=DashboardMetric(value=mcp_servers),
            im_entries=DashboardMetric(value=im_entries),
            runs=DashboardMetric(value=runs),
            active_runs=active_runs,
            service=DashboardServiceStatus(
                health="healthy" if not warnings else "degraded",
                database="available" if database_ok else "unavailable",
                redis="available" if redis_ok else "unavailable",
                runtime="in_process",
                environment=self.settings.app.environment,
            ),
            dependency_warnings=warnings,
        )
