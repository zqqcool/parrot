from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.modules.knowledge.media_models import KnowledgeMediaAsset
from app.modules.knowledge.models import KnowledgeDocument, KnowledgeDocumentVersion


class KnowledgeMediaRepository:
    """Tenant-scoped persistence for authorized knowledge-media metadata."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def downloadable(self, tenant_id: str, asset_id: str) -> KnowledgeMediaAsset | None:
        return await self.session.scalar(
            select(KnowledgeMediaAsset)
            .join(
                KnowledgeDocumentVersion,
                (KnowledgeDocumentVersion.tenant_id == KnowledgeMediaAsset.tenant_id)
                & (KnowledgeDocumentVersion.id == KnowledgeMediaAsset.document_version_id),
            )
            .join(
                KnowledgeDocument,
                (KnowledgeDocument.tenant_id == KnowledgeDocumentVersion.tenant_id)
                & (KnowledgeDocument.id == KnowledgeDocumentVersion.document_id),
            )
            .where(
                KnowledgeMediaAsset.tenant_id == tenant_id,
                KnowledgeMediaAsset.id == asset_id,
                KnowledgeMediaAsset.status == "ready",
                KnowledgeDocument.status == "active",
                KnowledgeDocumentVersion.status == "published",
            )
        )

    async def citation_assets(
        self,
        tenant_id: str,
        version_id: str,
        *,
        slide_no: int | None,
        group_id: str | None,
    ) -> tuple[KnowledgeMediaAsset, ...]:
        location = _location_filter(slide_no, group_id)
        if location is None:
            return ()
        rows = await self.session.scalars(
            select(KnowledgeMediaAsset)
            .where(
                KnowledgeMediaAsset.tenant_id == tenant_id,
                KnowledgeMediaAsset.document_version_id == version_id,
                KnowledgeMediaAsset.status == "ready",
                location,
            )
            .order_by(KnowledgeMediaAsset.ordinal_in_group, KnowledgeMediaAsset.id)
        )
        return tuple(rows)


def _location_filter(slide_no: int | None, group_id: str | None) -> ColumnElement[bool] | None:
    if slide_no is not None and group_id:
        return or_(
            KnowledgeMediaAsset.slide_no == slide_no,
            KnowledgeMediaAsset.group_id == group_id,
        )
    if slide_no is not None:
        return KnowledgeMediaAsset.slide_no == slide_no
    if group_id:
        return KnowledgeMediaAsset.group_id == group_id
    return None
