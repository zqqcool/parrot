from __future__ import annotations

from datetime import datetime
from typing import Protocol


class TaskDispatcher(Protocol):
    """Application port for durable TaskIQ delivery.

    Callers only provide tenant-scoped identifiers.  Task handlers reload and
    authorize state from PostgreSQL; no business payload or credential enters
    Redis.
    """

    async def dispatch_runtime(self, tenant_id: str, interaction_id: str) -> None: ...

    async def dispatch_memory_index(self, tenant_id: str, job_id: str) -> None: ...

    async def dispatch_knowledge_ingestion(self, tenant_id: str, job_id: str) -> None: ...

    async def dispatch_knowledge_vector(
        self, tenant_id: str, job_id: str, *, delay_seconds: int = 0
    ) -> None: ...

    async def dispatch_capability_index(
        self,
        tenant_id: str,
        source_kind: str,
        source_id: str,
        source_revision: str,
        *,
        delay_seconds: int = 0,
        attempt: int = 0,
    ) -> None: ...

    async def dispatch_skill_build(self, tenant_id: str, job_id: str) -> None: ...

    async def schedule_task(
        self,
        tenant_id: str,
        schedule_id: str,
        trigger_at: datetime,
    ) -> None: ...

    async def remove_schedule(self, schedule_id: str) -> None: ...
