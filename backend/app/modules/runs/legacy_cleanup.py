from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select

from app.infrastructure.db.session import DatabaseManager
from app.modules.runs.repository import RunRepository
from app.modules.tenancy.models import Tenant


@dataclass(frozen=True)
class LegacyRunCleanupSummary:
    tenant_id: str
    candidate_count: int
    deleted_count: int


class LegacyRunCleanupService:
    """Explicitly removes transcript-incompatible legacy WebSocket chat runs."""

    def __init__(self, database: DatabaseManager) -> None:
        self._database = database

    async def run(self, *, confirm: bool) -> tuple[LegacyRunCleanupSummary, ...]:
        async with self._database.platform_session() as session:
            tenant_ids = tuple(await session.scalars(select(Tenant.id)))
        summaries: list[LegacyRunCleanupSummary] = []
        for tenant_id in tenant_ids:
            async with self._database.session() as session:
                await self._database.set_tenant(session, tenant_id)
                repository = RunRepository(session)
                candidate_count = await repository.count_legacy_chat_runs(tenant_id)
                if confirm and candidate_count:
                    await repository.delete_legacy_chat_runs(tenant_id)
                summaries.append(
                    LegacyRunCleanupSummary(
                        tenant_id=tenant_id,
                        candidate_count=candidate_count,
                        deleted_count=candidate_count if confirm else 0,
                    )
                )
        return tuple(summaries)
