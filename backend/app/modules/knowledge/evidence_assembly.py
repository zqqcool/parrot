from __future__ import annotations

from collections.abc import Iterable

from app.core.config import AppConfig
from app.infrastructure.db.session import DatabaseManager
from app.modules.knowledge.evidence_expand import (
    EvidenceHit,
    ExpandBudget,
    expand_version_slides,
)
from app.modules.knowledge.evidence_repository import KnowledgeEvidenceRepository
from app.modules.knowledge.runtime_repository import (
    KnowledgeEvidenceRow,
)
from app.modules.knowledge.runtime_types import KnowledgeMediaRef

_StructureKey = tuple[str, str, str]


async def expand_evidence_bundle(
    database: DatabaseManager,
    *,
    tenant_id: str,
    agent_id: str,
    seed: list[KnowledgeEvidenceRow],
    scores: dict[str, float],
    settings: AppConfig | None,
    max_units: int | None = None,
    space_scoped: bool = False,
) -> tuple[list[KnowledgeEvidenceRow], dict[str, tuple[KnowledgeMediaRef, ...]]]:
    """Expand mixed structural hits while preserving version identity and global budgets."""
    if not seed:
        return seed, {}
    budget = _budget(settings, max_units=max_units)
    structural, plain = _selected_seed(seed, scores, budget.max_groups)
    slide_seed = [row for row in structural if getattr(row[0], "slide_no", None) is not None]
    group_seed = [row for row in structural if getattr(row[0], "slide_no", None) is None]
    slide_rows, slide_refs = await _expand_slide_hits(
        database,
        tenant_id=tenant_id,
        agent_id=agent_id,
        seed=slide_seed,
        scores=scores,
        budget=budget,
        space_scoped=space_scoped,
    )
    group_rows, group_refs = await _expand_group_hits(
        database,
        tenant_id=tenant_id,
        agent_id=agent_id,
        seed=group_seed,
        scores=scores,
        max_media=_max_media(settings),
        adjacent_window=budget.adjacent_window,
        max_groups=budget.max_groups,
        space_scoped=space_scoped,
    )
    eligible_seed = [*structural, *plain]
    ordered = _order_rows(eligible_seed, [*slide_rows, *group_rows], scores, budget.max_units)
    refs = limit_media_refs(ordered, {**slide_refs, **group_refs}, _max_media(settings))
    return ordered, refs


async def _expand_slide_hits(
    database: DatabaseManager,
    *,
    tenant_id: str,
    agent_id: str,
    seed: list[KnowledgeEvidenceRow],
    scores: dict[str, float],
    budget: ExpandBudget,
    space_scoped: bool,
) -> tuple[list[KnowledgeEvidenceRow], dict[str, tuple[KnowledgeMediaRef, ...]]]:
    if not seed:
        return [], {}
    hits = tuple(_slide_hit(row, scores) for row in seed)
    group_ids = tuple({hit.group_id for hit in hits if hit.group_id})
    async with database.session() as session:
        await database.set_tenant(session, tenant_id)
        repo = KnowledgeEvidenceRepository(session)
        group_slides = await repo.group_slide_map(tenant_id, group_ids)
        version_slides = expand_version_slides(hits, group_slides, budget)
        if space_scoped:
            expanded = await repo.published_chunks_for_slides(tenant_id, agent_id, version_slides)
        else:
            expanded = await repo.authorized_chunks_for_slides(tenant_id, agent_id, version_slides)
        ordered = order_slide_rows(seed, expanded, version_slides)
        media = await repo.slide_media_assets(tenant_id, version_slides)
    refs = {
        chunk.id: media.get((version.id, chunk.slide_no), ())
        for chunk, _document, version in ordered
        if chunk.slide_no is not None
    }
    return ordered, refs


async def _expand_group_hits(
    database: DatabaseManager,
    *,
    tenant_id: str,
    agent_id: str,
    seed: list[KnowledgeEvidenceRow],
    scores: dict[str, float],
    max_media: int,
    adjacent_window: int,
    max_groups: int,
    space_scoped: bool,
) -> tuple[list[KnowledgeEvidenceRow], dict[str, tuple[KnowledgeMediaRef, ...]]]:
    group_ids = _ranked_group_ids(seed, scores)
    if not group_ids:
        return [], {}
    async with database.session() as session:
        await database.set_tenant(session, tenant_id)
        repo = KnowledgeEvidenceRepository(session)
        group_ids = await repo.expanded_group_ids(
            tenant_id,
            group_ids,
            adjacent_window=adjacent_window,
            max_groups=max_groups,
        )
        if space_scoped:
            expanded = await repo.published_chunks_for_groups(tenant_id, agent_id, group_ids)
        else:
            expanded = await repo.authorized_chunks_for_groups(tenant_id, agent_id, group_ids)
        ordered = _order_group_rows(seed, expanded, group_ids)
        media = await repo.group_media_assets(tenant_id, group_ids, max_media=max_media)
    refs = {
        chunk.id: media.get(chunk.group_id, ())
        for chunk, _document, _version in ordered
        if chunk.group_id is not None
    }
    return ordered, refs


def _selected_seed(
    seed: list[KnowledgeEvidenceRow], scores: dict[str, float], max_groups: int
) -> tuple[list[KnowledgeEvidenceRow], list[KnowledgeEvidenceRow]]:
    ranked = sorted(seed, key=lambda row: (-scores.get(row[0].id, 0.0), row[0].id))
    selected_keys: set[_StructureKey] = set()
    for row in ranked:
        key = _structure_key(row)
        if key is None or key in selected_keys:
            continue
        if len(selected_keys) >= max_groups:
            break
        selected_keys.add(key)
    structural = [row for row in seed if _structure_key(row) in selected_keys]
    plain = [row for row in seed if _structure_key(row) is None]
    return structural, plain


def _slide_hit(row: KnowledgeEvidenceRow, scores: dict[str, float]) -> EvidenceHit:
    chunk, _document, version = row
    return EvidenceHit(
        chunk_id=chunk.id,
        group_id=chunk.group_id,
        slide_no=chunk.slide_no,
        page_kind=chunk.page_kind,
        score=scores.get(chunk.id, 0.0),
        document_version_id=version.id,
    )


def _ranked_group_ids(
    seed: list[KnowledgeEvidenceRow], scores: dict[str, float]
) -> tuple[str, ...]:
    ranked: list[str] = []
    seen: set[str] = set()
    for chunk, _document, _version in sorted(
        seed, key=lambda row: (-scores.get(row[0].id, 0.0), row[0].id)
    ):
        if not isinstance(chunk.group_id, str) or chunk.group_id in seen:
            continue
        ranked.append(chunk.group_id)
        seen.add(chunk.group_id)
    return tuple(ranked)


def order_slide_rows(
    seed: list[KnowledgeEvidenceRow],
    expanded: list[KnowledgeEvidenceRow],
    version_slides: tuple[tuple[str, int], ...],
) -> list[KnowledgeEvidenceRow]:
    by_locator: dict[tuple[str, int], KnowledgeEvidenceRow] = {}
    for row in [*expanded, *seed]:
        chunk, _document, version = row
        if chunk.slide_no is None:
            continue
        key = (version.id, chunk.slide_no)
        current = by_locator.get(key)
        if current is None or chunk.ordinal < current[0].ordinal:
            by_locator[key] = row
    return [by_locator[item] for item in version_slides if item in by_locator]


def _order_group_rows(
    seed: list[KnowledgeEvidenceRow],
    expanded: list[KnowledgeEvidenceRow],
    group_ids: tuple[str, ...],
) -> list[KnowledgeEvidenceRow]:
    by_group: dict[str, list[KnowledgeEvidenceRow]] = {}
    for row in [*expanded, *seed]:
        group_id = row[0].group_id
        if isinstance(group_id, str):
            by_group.setdefault(group_id, []).append(row)
    return _deduplicate_rows(
        row
        for group_id in group_ids
        for row in sorted(by_group.get(group_id, ()), key=lambda item: item[0].ordinal)
    )


def _order_rows(
    seed: list[KnowledgeEvidenceRow],
    expanded: list[KnowledgeEvidenceRow],
    scores: dict[str, float],
    max_units: int,
) -> list[KnowledgeEvidenceRow]:
    ranked_seed = sorted(seed, key=lambda row: (-scores.get(row[0].id, 0.0), row[0].id))
    priorities: dict[_StructureKey, int] = {}
    for index, row in enumerate(ranked_seed):
        priorities.setdefault(_row_key(row), index)
    candidates = _deduplicate_rows([*expanded, *seed])
    candidates.sort(
        key=lambda row: (
            priorities.get(_row_key(row), len(priorities)),
            row[0].ordinal,
            row[0].id,
        )
    )
    return candidates[:max_units]


def limit_media_refs(
    rows: list[KnowledgeEvidenceRow],
    refs: dict[str, tuple[KnowledgeMediaRef, ...]],
    maximum: int,
) -> dict[str, tuple[KnowledgeMediaRef, ...]]:
    limited: dict[str, tuple[KnowledgeMediaRef, ...]] = {}
    seen: set[str] = set()
    for chunk, _document, _version in rows:
        values = tuple(ref for ref in refs.get(chunk.id, ()) if ref.asset_id not in seen)
        values = values[: max(0, maximum - len(seen))]
        if values:
            limited[chunk.id] = values
            seen.update(ref.asset_id for ref in values)
        if len(seen) >= maximum:
            break
    return limited


def _structure_key(row: KnowledgeEvidenceRow) -> _StructureKey | None:
    chunk, _document, version = row
    if chunk.slide_no is not None:
        return ("slide", version.id, chunk.group_id or chunk.id)
    if chunk.group_id is not None:
        return ("group", version.id, chunk.group_id)
    return None


def _row_key(row: KnowledgeEvidenceRow) -> _StructureKey:
    return _structure_key(row) or ("plain", row[2].id, row[0].id)


def _deduplicate_rows(rows: Iterable[KnowledgeEvidenceRow]) -> list[KnowledgeEvidenceRow]:
    ordered: list[KnowledgeEvidenceRow] = []
    seen: set[str] = set()
    for row in rows:
        if row[0].id in seen:
            continue
        ordered.append(row)
        seen.add(row[0].id)
    return ordered


def _budget(settings: AppConfig | None, *, max_units: int | None = None) -> ExpandBudget:
    configured_max_units = settings.knowledge.evidence_max_units if settings is not None else 8
    return ExpandBudget(
        adjacent_window=(
            settings.knowledge.evidence_adjacent_window if settings is not None else 1
        ),
        max_groups=settings.knowledge.evidence_max_groups if settings is not None else 6,
        max_units=(
            min(configured_max_units, max_units) if max_units is not None else configured_max_units
        ),
    )


def _max_media(settings: AppConfig | None) -> int:
    return settings.knowledge.evidence_max_media if settings is not None else 8
