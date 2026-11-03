from __future__ import annotations

import asyncio
from datetime import timedelta

from sqlalchemy import update

from app.core.clock import utc_now
from app.infrastructure.db.session import DatabaseManager
from app.modules.interactions.models import Interaction


class InteractionLeaseHeartbeat:
    """Keeps an owned runtime lease alive until the executor settles the interaction."""

    def __init__(
        self,
        database: DatabaseManager,
        *,
        tenant_id: str,
        interaction_id: str,
        owner: str,
        lease_seconds: int,
        interval_seconds: float,
    ) -> None:
        self._database = database
        self._tenant_id = tenant_id
        self._interaction_id = interaction_id
        self._owner = owner
        self._lease_seconds = lease_seconds
        self._interval_seconds = interval_seconds
        self._task: asyncio.Task[None] | None = None
        self._lost = False

    @property
    def lost(self) -> bool:
        return self._lost

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        await asyncio.gather(self._task, return_exceptions=True)
        self._task = None

    async def renew(self) -> bool:
        async with self._database.session() as session:
            await self._database.set_tenant(session, self._tenant_id)
            result = await session.execute(
                update(Interaction)
                .where(
                    Interaction.tenant_id == self._tenant_id,
                    Interaction.id == self._interaction_id,
                    Interaction.status == "running",
                    Interaction.runtime_recovery_lease_owner == self._owner,
                )
                .values(
                    runtime_recovery_lease_until=utc_now() + timedelta(seconds=self._lease_seconds)
                )
                .returning(Interaction.id)
            )
            return result.scalar_one_or_none() is not None

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self._interval_seconds)
            if not await self.renew():
                self._lost = True
                return
