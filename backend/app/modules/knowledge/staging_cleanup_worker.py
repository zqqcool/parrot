from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import SYSTEM_CLOCK, Clock
from app.core.config import AppConfig
from app.core.object_storage import ObjectStoragePort
from app.infrastructure.db.session import DatabaseManager
from app.modules.audit.service import append_audit
from app.modules.iam.schemas import PrincipalContext
from app.modules.knowledge.models import KnowledgeSource

_CLEANUP_BATCH_SIZE = 100
_SYSTEM_SUBJECT_ID = "system:knowledge-staging-cleanup"


@dataclass(frozen=True)
class StaleKnowledgeSource:
    tenant_id: str
    source_id: str


class KnowledgeStagingCleanupWorker:
    """Remove expired, unconfirmed upload records from a bounded platform job."""

    def __init__(
        self,
        settings: AppConfig,
        object_storage: ObjectStoragePort,
        *,
        clock: Clock = SYSTEM_CLOCK,
    ) -> None:
        self._database = DatabaseManager(settings.database)
        self._storage = object_storage
        self._clock = clock
        self._retention_hours = settings.knowledge.staging_retention_hours

    async def close(self) -> None:
        await self._database.dispose()

    async def process(self) -> int:
        cutoff = self._clock.now() - timedelta(hours=self._retention_hours)
        candidates = await self._find_candidates(cutoff)
        deleted_count = 0
        for candidate in candidates:
            if await self._cleanup_candidate(candidate, cutoff):
                deleted_count += 1
        return deleted_count

    async def _find_candidates(self, cutoff: datetime) -> tuple[StaleKnowledgeSource, ...]:
        async with self._database.platform_session() as session:
            rows = await session.execute(
                select(KnowledgeSource.tenant_id, KnowledgeSource.id)
                .where(
                    KnowledgeSource.status == "staging",
                    KnowledgeSource.created_at < cutoff,
                )
                .order_by(KnowledgeSource.created_at, KnowledgeSource.id)
                .limit(_CLEANUP_BATCH_SIZE)
            )
            return tuple(
                StaleKnowledgeSource(tenant_id=tenant_id, source_id=source_id)
                for tenant_id, source_id in rows.tuples()
            )

    async def _cleanup_candidate(self, candidate: StaleKnowledgeSource, cutoff: datetime) -> bool:
        async with self._database.session() as session:
            await self._database.set_tenant(session, candidate.tenant_id)
            source = await _stale_source_for_update(
                session, candidate.tenant_id, candidate.source_id, cutoff
            )
            if source is None:
                return False
            if source.staging_key is not None:
                await self._storage.delete(source.staging_key)
            await session.delete(source)
            append_audit(
                session,
                _system_principal(candidate.tenant_id),
                "knowledge.source.staging.expire",
                "knowledge_source",
                candidate.source_id,
                {"space_id": source.space_id},
                tenant_id=candidate.tenant_id,
            )
            return True


async def _stale_source_for_update(
    session: AsyncSession,
    tenant_id: str,
    source_id: str,
    cutoff: datetime,
) -> KnowledgeSource | None:
    return await session.scalar(
        select(KnowledgeSource)
        .where(
            KnowledgeSource.tenant_id == tenant_id,
            KnowledgeSource.id == source_id,
            KnowledgeSource.status == "staging",
            KnowledgeSource.created_at < cutoff,
        )
        .with_for_update(skip_locked=True)
    )


def _system_principal(tenant_id: str) -> PrincipalContext:
    return PrincipalContext(
        tenant_id=tenant_id,
        subject_type="system",
        subject_id=_SYSTEM_SUBJECT_ID,
        username="system",
        display_name="Knowledge staging cleanup",
        permissions=(),
        tenants=(),
        must_change_password=False,
        request_id="taskiq:knowledge-staging-cleanup",
    )
