from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.errors import AppError
from app.infrastructure.db.session import DatabaseManager
from app.modules.iam.schemas import PrincipalContext
from app.modules.knowledge.access import KnowledgeAccessPolicy
from app.modules.knowledge.media_repository import KnowledgeMediaRepository
from app.modules.knowledge.repository import KnowledgeRepository
from app.modules.knowledge.runtime_types import KnowledgeMediaRef
from app.modules.knowledge.schemas import (
    KnowledgeCitationView,
    KnowledgeMediaRefView,
    knowledge_media_ref_view,
)


class KnowledgeCitationService:
    def __init__(self, session: AsyncSession, database: DatabaseManager) -> None:
        self.session = session
        self.database = database
        self.repository = KnowledgeRepository(session)
        self.media = KnowledgeMediaRepository(session)
        self.access_policy = KnowledgeAccessPolicy(session, database)

    async def expand(
        self, principal: PrincipalContext, tenant_id: str, citation_id: str
    ) -> KnowledgeCitationView:
        await self._enter(principal, tenant_id)
        row = await self.repository.citation(tenant_id, citation_id)
        if row is None:
            raise AppError(
                "RESOURCE_NOT_FOUND", "Knowledge citation not found", status.HTTP_404_NOT_FOUND
            )
        chunk, document, version = row
        if not await self.repository.user_has_access(
            tenant_id, chunk.space_id, principal.subject_id
        ):
            raise AppError(
                "RESOURCE_NOT_FOUND", "Knowledge citation not found", status.HTTP_404_NOT_FOUND
            )
        slide_no = getattr(chunk, "slide_no", None)
        group_id = getattr(chunk, "group_id", None)
        media_refs = await self._media_refs(
            tenant_id, version.id, slide_no=slide_no, group_id=group_id
        )
        return KnowledgeCitationView(
            citation_id=chunk.id,
            document_id=document.id,
            document_version_id=version.id,
            title=document.title,
            citation_anchor=chunk.citation_anchor,
            excerpt=_bounded(chunk.content),
            content_chars=len(chunk.content),
            content=chunk.content,
            slide_no=slide_no,
            media_refs=media_refs,
        )

    async def _media_refs(
        self,
        tenant_id: str,
        version_id: str,
        *,
        slide_no: int | None,
        group_id: str | None,
    ) -> tuple[KnowledgeMediaRefView, ...]:
        rows = await self.media.citation_assets(
            tenant_id, version_id, slide_no=slide_no, group_id=group_id
        )
        return tuple(
            knowledge_media_ref_view(
                KnowledgeMediaRef(
                    asset_id=asset.id,
                    slide_no=asset.slide_no,
                    sheet_name=asset.sheet_name,
                    cell_anchor=asset.cell_anchor,
                    section_path=asset.section_path,
                    asset_kind=asset.asset_kind,
                    ordinal=asset.ordinal_in_group,
                )
            )
            for asset in rows
        )

    async def _enter(self, principal: PrincipalContext, tenant_id: str) -> None:
        await self.access_policy.enter(
            principal,
            tenant_id,
            "knowledge.query",
            not_found_message="Knowledge citation not found",
        )


def _bounded(value: str, maximum: int = 4_000) -> str:
    return value if len(value) <= maximum else f"{value[: maximum - 1].rstrip()}…"
