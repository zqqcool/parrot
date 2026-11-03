from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import new_id
from app.core.task_dispatch import TaskDispatcher
from app.modules.memory.models import MemoryIndexJob, MemoryRecord


async def enqueue_memory_index(
    session: AsyncSession,
    memory: MemoryRecord,
    *,
    action: str,
    dispatcher: TaskDispatcher | None = None,
) -> MemoryIndexJob:
    """Record a vector operation and deliver its identifier through TaskIQ."""
    job = MemoryIndexJob(
        id=new_id("memory_index"),
        tenant_id=memory.tenant_id,
        memory_id=memory.id,
        memory_version=memory.version,
        action=action,
    )
    session.add(job)
    await session.flush()
    if dispatcher is not None:
        await dispatcher.dispatch_memory_index(memory.tenant_id, job.id)
    return job
