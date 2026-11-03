from __future__ import annotations

from types import SimpleNamespace
from typing import cast

from app.modules.knowledge.evidence_assembly import limit_media_refs, order_slide_rows
from app.modules.knowledge.evidence_expand import (
    EvidenceHit,
    ExpandBudget,
    expand_slide_numbers,
    expand_version_slides,
)
from app.modules.knowledge.evidence_repository import expanded_group_order
from app.modules.knowledge.media_models import KnowledgeEvidenceGroup
from app.modules.knowledge.rendering import PillowSlideRenderer
from app.modules.knowledge.runtime_repository import KnowledgeEvidenceRow
from app.modules.knowledge.runtime_types import KnowledgeMediaRef


def test_expand_short_chapter_returns_all_slides() -> None:
    hits = (
        EvidenceHit("c2", "g1", 10, "operation", 0.9),
        EvidenceHit("c1", "g1", 9, "operation", 0.5),
    )
    slides = expand_slide_numbers(
        hits,
        {"g1": (9, 10, 11)},
        ExpandBudget(adjacent_window=1, max_groups=6, max_units=8),
    )
    assert slides == (9, 10, 11)


def test_expand_long_chapter_uses_adjacent_window() -> None:
    hits = (EvidenceHit("c1", "g1", 30, "operation", 1.0),)
    members = tuple(range(27, 47))
    slides = expand_slide_numbers(
        hits,
        {"g1": members},
        ExpandBudget(adjacent_window=1, max_groups=6, max_units=8),
    )
    assert slides == (29, 30, 31)


def test_expand_diagram_includes_next_table_page() -> None:
    hits = (EvidenceHit("c1", "g1", 3, "diagram", 1.0),)
    slides = expand_slide_numbers(
        hits,
        {"g1": (3, 4, 5, 6, 7, 8)},
        ExpandBudget(adjacent_window=1, max_groups=6, max_units=8),
    )
    assert 3 in slides and 4 in slides


def test_expand_slides_preserves_document_version_identity() -> None:
    hits = (
        EvidenceHit("a", "group_a", 3, "operation", 1.0, "version_a"),
        EvidenceHit("b", "group_b", 3, "operation", 0.9, "version_b"),
    )

    selected = expand_version_slides(
        hits,
        {"group_a": (2, 3, 4), "group_b": (3, 4, 5)},
        ExpandBudget(max_groups=6, max_units=8),
    )

    assert selected == (
        ("version_a", 2),
        ("version_a", 3),
        ("version_a", 4),
        ("version_b", 3),
        ("version_b", 4),
        ("version_b", 5),
    )


def test_slide_order_keeps_same_slide_number_from_distinct_versions() -> None:
    row_a = _row("chunk_a", "version_a", slide_no=3)
    row_b = _row("chunk_b", "version_b", slide_no=3)

    ordered = order_slide_rows([row_a, row_b], [], (("version_a", 3), ("version_b", 3)))

    assert [row[0].id for row in ordered] == ["chunk_a", "chunk_b"]


def test_media_budget_is_global_and_deduplicates_group_refs() -> None:
    row_a = _row("chunk_a", "version_a", group_id="group_a")
    row_b = _row("chunk_b", "version_a", group_id="group_a")
    refs = (
        KnowledgeMediaRef("media_1"),
        KnowledgeMediaRef("media_2"),
        KnowledgeMediaRef("media_3"),
    )

    limited = limit_media_refs([row_a, row_b], {"chunk_a": refs, "chunk_b": refs}, maximum=2)

    assert [item.asset_id for item in limited["chunk_a"]] == ["media_1", "media_2"]
    assert "chunk_b" not in limited


def test_adjacent_group_expansion_never_drops_direct_hits() -> None:
    groups = tuple(_evidence_group(f"group_{index}", ordinal=index) for index in range(1, 5))

    expanded = expanded_group_order(
        ("group_2", "group_4"),
        {group.id: group for group in groups},
        groups,
        adjacent_window=1,
        max_groups=3,
    )

    assert expanded[:2] == ("group_2", "group_4")
    assert len(expanded) == 3


def test_pillow_renderer_prefers_embedded_image() -> None:
    from io import BytesIO

    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", (40, 20), color=(255, 0, 0)).save(buffer, format="PNG")
    rendered = PillowSlideRenderer().render_preview(
        slide_no=1,
        title="Login",
        body="unused",
        embedded=(buffer.getvalue(),),
    )
    assert rendered.content_type == "image/png"
    assert rendered.full_slide is False
    assert rendered.content.startswith(b"\x89PNG")


def test_pillow_renderer_builds_text_card_without_embedded() -> None:
    rendered = PillowSlideRenderer().render_preview(
        slide_no=3,
        title="Architecture",
        body="Onboarding\nContract",
        embedded=(),
    )
    assert rendered.content_type == "image/png"
    assert rendered.full_slide is False
    assert len(rendered.content) > 100


def _row(
    chunk_id: str,
    version_id: str,
    *,
    slide_no: int | None = None,
    group_id: str | None = None,
) -> KnowledgeEvidenceRow:
    return cast(
        KnowledgeEvidenceRow,
        (
            SimpleNamespace(
                id=chunk_id,
                ordinal=1,
                slide_no=slide_no,
                group_id=group_id,
                page_kind=None,
            ),
            SimpleNamespace(id=f"document_{version_id}"),
            SimpleNamespace(id=version_id),
        ),
    )


def _evidence_group(group_id: str, *, ordinal: int) -> KnowledgeEvidenceGroup:
    return KnowledgeEvidenceGroup(
        id=group_id,
        tenant_id="tenant_1",
        space_id="space_1",
        document_version_id="version_1",
        kind="procedure_step",
        title=group_id,
        expand_default="adjacent_1",
        ordinal_start=ordinal,
        ordinal_end=ordinal,
    )
