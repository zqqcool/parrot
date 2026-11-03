from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EvidenceHit:
    chunk_id: str
    group_id: str | None
    slide_no: int | None
    page_kind: str | None
    score: float
    document_version_id: str | None = None


@dataclass(frozen=True)
class ExpandBudget:
    adjacent_window: int = 1
    max_groups: int = 6
    max_units: int = 8


def expand_slide_numbers(
    hits: tuple[EvidenceHit, ...],
    group_slides: dict[str, tuple[int, ...]],
    budget: ExpandBudget,
) -> tuple[int, ...]:
    """Return ordered slide numbers to include after adjacent/chapter expansion."""
    if not hits:
        return ()
    selected: list[int] = []
    seen_slides: set[int] = set()
    for group_id, hit_slide, page_kind in _ranked_groups(hits)[: budget.max_groups]:
        members = _group_members(group_id, hit_slide, group_slides)
        if not members:
            continue
        chosen = _choose_slides(members, hit_slide, page_kind, budget)
        for slide in chosen:
            if slide in seen_slides:
                continue
            selected.append(slide)
            seen_slides.add(slide)
            if len(selected) >= budget.max_units:
                return tuple(selected)
    return tuple(selected)


def expand_version_slides(
    hits: tuple[EvidenceHit, ...],
    group_slides: dict[str, tuple[int, ...]],
    budget: ExpandBudget,
) -> tuple[tuple[str, int], ...]:
    """Expand slide hits without losing their immutable document-version identity."""
    selected: list[tuple[str, int]] = []
    seen: set[tuple[str, int]] = set()
    for hit in _ranked_version_groups(hits)[: budget.max_groups]:
        if hit.document_version_id is None:
            continue
        members = _group_members(hit.group_id, hit.slide_no, group_slides)
        for slide in _choose_slides(members, hit.slide_no, hit.page_kind, budget):
            item = (hit.document_version_id, slide)
            if item in seen:
                continue
            selected.append(item)
            seen.add(item)
            if len(selected) >= budget.max_units:
                return tuple(selected)
    return tuple(selected)


def _ranked_groups(
    hits: tuple[EvidenceHit, ...],
) -> list[tuple[str | None, int | None, str | None]]:
    ranked: list[tuple[str | None, int | None, str | None]] = []
    seen: set[str | None] = set()
    for hit in sorted(hits, key=lambda item: (-item.score, item.chunk_id)):
        if hit.group_id in seen:
            continue
        seen.add(hit.group_id)
        ranked.append((hit.group_id, hit.slide_no, hit.page_kind))
    return ranked


def _ranked_version_groups(hits: tuple[EvidenceHit, ...]) -> list[EvidenceHit]:
    ranked: list[EvidenceHit] = []
    seen: set[tuple[str | None, str | None]] = set()
    for hit in sorted(hits, key=lambda item: (-item.score, item.chunk_id)):
        key = (hit.document_version_id, hit.group_id or hit.chunk_id)
        if key in seen:
            continue
        seen.add(key)
        ranked.append(hit)
    return ranked


def _group_members(
    group_id: str | None,
    hit_slide: int | None,
    group_slides: dict[str, tuple[int, ...]],
) -> list[int]:
    members = list(group_slides.get(group_id or "", ()))
    if hit_slide is not None and hit_slide not in members:
        members = sorted({*members, hit_slide})
    if not members and hit_slide is not None:
        return [hit_slide]
    return members


def _choose_slides(
    members: list[int],
    hit_slide: int | None,
    page_kind: str | None,
    budget: ExpandBudget,
) -> list[int]:
    if len(members) <= 3:
        return members
    if hit_slide is None:
        return members[: budget.adjacent_window * 2 + 1]
    window = budget.adjacent_window
    chosen = [slide for slide in members if abs(slide - hit_slide) <= window]
    if page_kind == "diagram":
        nxt = next((slide for slide in members if slide > hit_slide), None)
        if nxt is not None and nxt not in chosen:
            chosen.append(nxt)
    return sorted(chosen)
