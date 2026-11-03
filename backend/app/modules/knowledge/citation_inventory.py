from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.session import DatabaseManager
from app.modules.agent_runtime.knowledge_output import KnowledgeCitationInventoryItem
from app.modules.knowledge.media_repository import KnowledgeMediaRepository
from app.modules.knowledge.repository import KnowledgeRepository
from app.modules.knowledge.runtime_types import KnowledgeMediaRef


class KnowledgeCitationInventoryHydrator:
    """Load citation metadata + primary media for terminal output assembly."""

    def __init__(self, session: AsyncSession, database: DatabaseManager) -> None:
        self.session = session
        self.database = database
        self.repository = KnowledgeRepository(session)
        self.media = KnowledgeMediaRepository(session)

    async def hydrate(
        self, tenant_id: str, citation_ids: tuple[str, ...]
    ) -> tuple[KnowledgeCitationInventoryItem, ...]:
        if not citation_ids:
            return ()
        await self.database.set_tenant(self.session, tenant_id)
        items: list[KnowledgeCitationInventoryItem] = []
        seen: set[str] = set()
        for citation_id in citation_ids:
            resolved = await self._resolve_id(tenant_id, citation_id)
            if resolved is None or resolved in seen:
                continue
            seen.add(resolved)
            row = await self.repository.citation(tenant_id, resolved)
            if row is None:
                continue
            chunk, document, version = row
            refs = await self._media_refs(
                tenant_id,
                version.id,
                slide_no=getattr(chunk, "slide_no", None),
                group_id=getattr(chunk, "group_id", None),
            )
            primary = _primary_media(refs)
            slide_no = getattr(chunk, "slide_no", None)
            items.append(
                KnowledgeCitationInventoryItem(
                    citation_id=chunk.id,
                    title=document.title,
                    anchor=chunk.citation_anchor,
                    slide_no=slide_no if isinstance(slide_no, int) else None,
                    space_id=chunk.space_id,
                    has_media=primary is not None,
                    primary_media_kind=None if primary is None else primary.asset_kind,
                    primary_asset_id=None if primary is None else primary.asset_id,
                    primary_alt=_media_alt(document.title, chunk.citation_anchor, primary),
                )
            )
        return tuple(items)

    async def _resolve_id(self, tenant_id: str, citation_id: str) -> str | None:
        candidates = (citation_id,)
        if not citation_id.startswith("knowledge_chunk_"):
            candidates = (f"knowledge_chunk_{citation_id}", citation_id)
        for candidate in candidates:
            row = await self.repository.citation(tenant_id, candidate)
            if row is not None:
                return candidate
        return None

    async def _media_refs(
        self,
        tenant_id: str,
        version_id: str,
        *,
        slide_no: int | None,
        group_id: str | None,
    ) -> tuple[KnowledgeMediaRef, ...]:
        assets = await self.media.citation_assets(
            tenant_id, version_id, slide_no=slide_no, group_id=group_id
        )
        return tuple(
            KnowledgeMediaRef(
                asset_id=asset.id,
                slide_no=asset.slide_no,
                sheet_name=asset.sheet_name,
                cell_anchor=asset.cell_anchor,
                section_path=asset.section_path,
                asset_kind=asset.asset_kind,
                ordinal=asset.ordinal_in_group,
            )
            for asset in assets
        )


def _primary_media(refs: tuple[KnowledgeMediaRef, ...]) -> KnowledgeMediaRef | None:
    if not refs:
        return None
    for kind in ("slide_render", "thumb", "embedded"):
        pool = tuple(ref for ref in refs if ref.asset_kind == kind)
        if pool:
            return min(pool, key=lambda ref: (ref.ordinal, ref.asset_id))
    return min(refs, key=lambda ref: (ref.ordinal, ref.asset_id))


def _media_alt(
    title: str, anchor: str, primary: KnowledgeMediaRef | None
) -> str | None:
    if primary is None:
        return None
    if primary.slide_no is not None:
        return f"{title} · 第 {primary.slide_no} 页"
    if anchor:
        return f"{title} · {anchor}"
    return title
