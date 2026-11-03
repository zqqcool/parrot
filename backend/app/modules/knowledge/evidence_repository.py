from __future__ import annotations

from collections.abc import Mapping

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from app.modules.knowledge.media_models import KnowledgeEvidenceGroup, KnowledgeMediaAsset
from app.modules.knowledge.models import KnowledgeChunk, KnowledgeDocument, KnowledgeDocumentVersion
from app.modules.knowledge.runtime_repository import (
    KnowledgeEvidenceRow,
    KnowledgeRuntimeRepository,
)
from app.modules.knowledge.runtime_types import KnowledgeMediaRef


class KnowledgeEvidenceRepository:
    """Authorized persistence queries used only by structural evidence expansion."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.runtime = KnowledgeRuntimeRepository(session)

    async def group_slide_map(
        self, tenant_id: str, group_ids: tuple[str, ...]
    ) -> dict[str, tuple[int, ...]]:
        if not group_ids:
            return {}
        rows = await self.session.execute(
            select(KnowledgeChunk.group_id, KnowledgeChunk.slide_no)
            .where(
                KnowledgeChunk.tenant_id == tenant_id,
                KnowledgeChunk.group_id.in_(group_ids),
                KnowledgeChunk.slide_no.is_not(None),
            )
            .order_by(KnowledgeChunk.group_id, KnowledgeChunk.slide_no, KnowledgeChunk.ordinal)
        )
        mapping: dict[str, list[int]] = {}
        for group_id, slide_no in rows.tuples():
            if isinstance(group_id, str) and isinstance(slide_no, int):
                bucket = mapping.setdefault(group_id, [])
                if not bucket or bucket[-1] != slide_no:
                    bucket.append(slide_no)
        return {key: tuple(values) for key, values in mapping.items()}

    async def authorized_chunks_for_slides(
        self,
        tenant_id: str,
        agent_id: str,
        version_slides: tuple[tuple[str, int], ...],
    ) -> list[KnowledgeEvidenceRow]:
        return await self._chunks_for_slides(
            self.runtime.authorized_statement(tenant_id, agent_id), version_slides
        )

    async def published_chunks_for_slides(
        self,
        tenant_id: str,
        space_id: str,
        version_slides: tuple[tuple[str, int], ...],
    ) -> list[KnowledgeEvidenceRow]:
        return await self._chunks_for_slides(
            self.runtime.published_space_statement(tenant_id, space_id), version_slides
        )

    async def _chunks_for_slides(
        self,
        statement: Select[tuple[KnowledgeChunk, KnowledgeDocument, KnowledgeDocumentVersion]],
        version_slides: tuple[tuple[str, int], ...],
    ) -> list[KnowledgeEvidenceRow]:
        if not version_slides:
            return []
        version_ids = tuple({version_id for version_id, _slide in version_slides})
        slide_nos = tuple({slide for _version, slide in version_slides})
        rows = await self.session.execute(
            statement.where(
                KnowledgeChunk.document_version_id.in_(version_ids),
                KnowledgeChunk.slide_no.in_(slide_nos),
            )
        )
        wanted = set(version_slides)
        return [
            (chunk, document, version)
            for chunk, document, version in rows.tuples()
            if chunk.slide_no is not None and (version.id, chunk.slide_no) in wanted
        ]

    async def slide_media_assets(
        self, tenant_id: str, version_slides: tuple[tuple[str, int], ...]
    ) -> dict[tuple[str, int], tuple[KnowledgeMediaRef, ...]]:
        if not version_slides:
            return {}
        version_ids = tuple({version_id for version_id, _slide in version_slides})
        slide_nos = tuple({slide for _version, slide in version_slides})
        rows = await self.session.scalars(
            select(KnowledgeMediaAsset)
            .where(
                KnowledgeMediaAsset.tenant_id == tenant_id,
                KnowledgeMediaAsset.document_version_id.in_(version_ids),
                KnowledgeMediaAsset.slide_no.in_(slide_nos),
                KnowledgeMediaAsset.asset_kind.in_(("slide_render", "thumb")),
                KnowledgeMediaAsset.status == "ready",
            )
            .order_by(
                KnowledgeMediaAsset.document_version_id,
                KnowledgeMediaAsset.slide_no,
                KnowledgeMediaAsset.ordinal_in_group,
            )
        )
        return _slide_media_map(tuple(rows), set(version_slides))

    async def authorized_chunks_for_groups(
        self, tenant_id: str, agent_id: str, group_ids: tuple[str, ...]
    ) -> list[KnowledgeEvidenceRow]:
        return await self._chunks_for_groups(
            self.runtime.authorized_statement(tenant_id, agent_id), group_ids
        )

    async def published_chunks_for_groups(
        self, tenant_id: str, space_id: str, group_ids: tuple[str, ...]
    ) -> list[KnowledgeEvidenceRow]:
        return await self._chunks_for_groups(
            self.runtime.published_space_statement(tenant_id, space_id), group_ids
        )

    async def _chunks_for_groups(
        self,
        statement: Select[tuple[KnowledgeChunk, KnowledgeDocument, KnowledgeDocumentVersion]],
        group_ids: tuple[str, ...],
    ) -> list[KnowledgeEvidenceRow]:
        if not group_ids:
            return []
        rows = await self.session.execute(
            statement.where(KnowledgeChunk.group_id.in_(group_ids)).order_by(KnowledgeChunk.ordinal)
        )
        wanted = set(group_ids)
        return [
            (chunk, document, version)
            for chunk, document, version in rows.tuples()
            if chunk.group_id in wanted
        ]

    async def expanded_group_ids(
        self,
        tenant_id: str,
        group_ids: tuple[str, ...],
        *,
        adjacent_window: int,
        max_groups: int,
    ) -> tuple[str, ...]:
        if not group_ids:
            return ()
        selected_rows = tuple(
            await self.session.scalars(
                select(KnowledgeEvidenceGroup).where(
                    KnowledgeEvidenceGroup.tenant_id == tenant_id,
                    KnowledgeEvidenceGroup.id.in_(group_ids),
                )
            )
        )
        selected = {item.id: item for item in selected_rows}
        procedure_rows = await self._procedure_groups(
            tenant_id, tuple({item.document_version_id for item in selected_rows})
        )
        return expanded_group_order(
            group_ids,
            selected,
            procedure_rows,
            adjacent_window=adjacent_window,
            max_groups=max_groups,
        )

    async def _procedure_groups(
        self, tenant_id: str, version_ids: tuple[str, ...]
    ) -> tuple[KnowledgeEvidenceGroup, ...]:
        if not version_ids:
            return ()
        rows = await self.session.scalars(
            select(KnowledgeEvidenceGroup)
            .where(
                KnowledgeEvidenceGroup.tenant_id == tenant_id,
                KnowledgeEvidenceGroup.document_version_id.in_(version_ids),
                KnowledgeEvidenceGroup.kind == "procedure_step",
            )
            .order_by(
                KnowledgeEvidenceGroup.document_version_id,
                KnowledgeEvidenceGroup.ordinal_start,
                KnowledgeEvidenceGroup.id,
            )
        )
        return tuple(rows)

    async def group_media_assets(
        self, tenant_id: str, group_ids: tuple[str, ...], *, max_media: int
    ) -> dict[str, tuple[KnowledgeMediaRef, ...]]:
        if not group_ids:
            return {}
        rows = await self.session.scalars(
            select(KnowledgeMediaAsset)
            .where(
                KnowledgeMediaAsset.tenant_id == tenant_id,
                KnowledgeMediaAsset.group_id.in_(group_ids),
                KnowledgeMediaAsset.status == "ready",
            )
            .order_by(
                KnowledgeMediaAsset.group_id,
                KnowledgeMediaAsset.ordinal_in_group,
                KnowledgeMediaAsset.id,
            )
        )
        return _limited_group_media(tuple(rows), group_ids, max_media)


def expanded_group_order(
    group_ids: tuple[str, ...],
    selected: Mapping[str, KnowledgeEvidenceGroup],
    procedure_rows: tuple[KnowledgeEvidenceGroup, ...],
    *,
    adjacent_window: int,
    max_groups: int,
) -> tuple[str, ...]:
    if max_groups <= 0:
        return ()
    by_version: dict[str, list[KnowledgeEvidenceGroup]] = {}
    for item in procedure_rows:
        by_version.setdefault(item.document_version_id, []).append(item)
    # Reserve the budget for direct hits first. Otherwise the adjacent groups of
    # an early hit can consume the whole budget and silently drop a later hit.
    expanded = list(dict.fromkeys(group_ids))[:max_groups]
    for group_id in group_ids:
        item = selected.get(group_id)
        if item is None:
            continue
        candidates = _adjacent_groups(item, by_version, adjacent_window)
        for candidate in candidates:
            if candidate.id not in expanded:
                expanded.append(candidate.id)
            if len(expanded) >= max_groups:
                return tuple(expanded)
    return tuple(expanded)


def _adjacent_groups(
    item: KnowledgeEvidenceGroup,
    by_version: dict[str, list[KnowledgeEvidenceGroup]],
    window: int,
) -> list[KnowledgeEvidenceGroup]:
    if item.kind != "procedure_step":
        return [item]
    siblings = by_version.get(item.document_version_id, [])
    index = next((i for i, value in enumerate(siblings) if value.id == item.id), -1)
    if index < 0:
        return [item]
    return siblings[max(0, index - window) : index + window + 1]


def _slide_media_map(
    assets: tuple[KnowledgeMediaAsset, ...], wanted: set[tuple[str, int]]
) -> dict[tuple[str, int], tuple[KnowledgeMediaRef, ...]]:
    mapping: dict[tuple[str, int], list[KnowledgeMediaRef]] = {}
    for asset in assets:
        if asset.slide_no is None:
            continue
        key = (asset.document_version_id, asset.slide_no)
        if key in wanted:
            mapping.setdefault(key, []).append(_media_ref(asset))
    return {key: tuple(values) for key, values in mapping.items()}


def _limited_group_media(
    assets: tuple[KnowledgeMediaAsset, ...], group_ids: tuple[str, ...], maximum: int
) -> dict[str, tuple[KnowledgeMediaRef, ...]]:
    mapping: dict[str, list[KnowledgeMediaRef]] = {}
    for asset in assets:
        if asset.group_id is not None:
            mapping.setdefault(asset.group_id, []).append(_media_ref(asset))
    limited: dict[str, tuple[KnowledgeMediaRef, ...]] = {}
    remaining = maximum
    for group_id in group_ids:
        values = tuple(mapping.get(group_id, ()))[:remaining]
        if values:
            limited[group_id] = values
            remaining -= len(values)
        if remaining <= 0:
            break
    return limited


def _media_ref(asset: KnowledgeMediaAsset) -> KnowledgeMediaRef:
    return KnowledgeMediaRef(
        asset_id=asset.id,
        slide_no=asset.slide_no,
        sheet_name=asset.sheet_name,
        cell_anchor=asset.cell_anchor,
        section_path=asset.section_path,
        asset_kind=asset.asset_kind,
        ordinal=asset.ordinal_in_group,
    )
