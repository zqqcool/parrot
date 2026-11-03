from __future__ import annotations

from app.infrastructure.db.session import DatabaseManager
from app.modules.agent_runtime.knowledge_output import KnowledgeCitationInventoryItem
from app.modules.knowledge.citation_inventory import KnowledgeCitationInventoryHydrator


class SessionBoundCitationHydrator:
    """Open a short-lived DB session to hydrate citations for terminal assembly."""

    def __init__(self, database: DatabaseManager) -> None:
        self._database = database

    async def hydrate(
        self, tenant_id: str, citation_ids: tuple[str, ...]
    ) -> tuple[KnowledgeCitationInventoryItem, ...]:
        async with self._database.session() as session:
            return await KnowledgeCitationInventoryHydrator(session, self._database).hydrate(
                tenant_id, citation_ids
            )
