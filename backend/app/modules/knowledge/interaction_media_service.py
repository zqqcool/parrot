from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status
from typing import cast

from app.core.errors import AppError
from app.core.object_storage import ObjectStoragePort
from app.infrastructure.db.session import DatabaseManager
from app.modules.interactions.models import Interaction, InteractionEvent
from app.modules.knowledge.media_repository import KnowledgeMediaRepository
from app.modules.knowledge.media_types import media_file_extension


@dataclass(frozen=True)
class InteractionKnowledgeMediaFile:
    filename: str
    content_type: str
    content: bytes


class InteractionKnowledgeMediaService:
    """Serve knowledge media only when an owned interaction already released the asset."""

    def __init__(
        self,
        session: AsyncSession,
        database: DatabaseManager,
        object_storage: ObjectStoragePort | None,
    ) -> None:
        self.session = session
        self.database = database
        self.storage = object_storage
        self.media = KnowledgeMediaRepository(session)

    async def download(
        self,
        *,
        tenant_id: str,
        actor_type: str,
        actor_id: str,
        interaction_id: str,
        asset_id: str,
    ) -> InteractionKnowledgeMediaFile:
        await self.database.set_tenant(self.session, tenant_id)
        interaction = await self.session.scalar(
            select(Interaction).where(
                Interaction.id == interaction_id,
                Interaction.tenant_id == tenant_id,
                Interaction.actor_type == actor_type,
                Interaction.actor_id == actor_id,
                Interaction.runtime_depth == 0,
            )
        )
        released = await self._asset_released(tenant_id, interaction_id, asset_id)
        if interaction is None or not released:
            raise AppError(
                "RESOURCE_NOT_FOUND",
                "Knowledge media asset not found",
                status.HTTP_404_NOT_FOUND,
            )
        if self.storage is None:
            raise AppError(
                "KNOWLEDGE_SOURCE_UNAVAILABLE",
                "Knowledge source is temporarily unavailable",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        asset = await self.media.downloadable(tenant_id, asset_id)
        if asset is None:
            raise AppError(
                "RESOURCE_NOT_FOUND",
                "Knowledge media asset not found",
                status.HTTP_404_NOT_FOUND,
            )
        stored = await self.storage.read(asset.object_key)
        if stored is None:
            raise AppError(
                "RESOURCE_NOT_FOUND",
                "Knowledge media asset not found",
                status.HTTP_404_NOT_FOUND,
            )
        extension = media_file_extension(asset.content_type)
        return InteractionKnowledgeMediaFile(
            filename=f"{asset.asset_kind}-{asset.slide_no or 0}{extension}",
            content_type=asset.content_type,
            content=stored.content,
        )

    async def _asset_released(self, tenant_id: str, interaction_id: str, asset_id: str) -> bool:
        events = await self.session.scalars(
            select(InteractionEvent).where(
                InteractionEvent.tenant_id == tenant_id,
                InteractionEvent.interaction_id == interaction_id,
                InteractionEvent.type == "ai.output.completed",
            )
        )
        for event in events:
            media = event.data.get("media")
            if not isinstance(media, list):
                continue
            for raw in cast(list[object], media):
                if not isinstance(raw, dict):
                    continue
                typed = cast(dict[str, object], raw)
                if typed.get("asset_id") == asset_id:
                    return True
        return False
