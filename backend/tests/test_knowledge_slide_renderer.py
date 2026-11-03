from __future__ import annotations

from app.modules.knowledge.extraction.types import ExtractedBlock, ExtractedDocument
from app.modules.knowledge.ingestion_publish import prepare_slide_media
from app.modules.knowledge.rendering.libreoffice_slide_renderer import CompositeSlideRenderer
from app.modules.knowledge.rendering.pillow_slide_renderer import PillowSlideRenderer
from app.modules.knowledge.rendering.port import RenderedSlide


def test_composite_renderer_falls_back_to_pillow_without_soffice() -> None:
    renderer = CompositeSlideRenderer(
        pillow=PillowSlideRenderer(width=320, height=180),
        soffice_bin="/nonexistent/soffice",
        enabled=True,
    )
    renderer.prepare_deck(b"not-a-pptx")
    rendered = renderer.render_preview(
        slide_no=1,
        title="Architecture",
        body="Fallback text card",
    )
    assert rendered.content_type == "image/png"
    assert rendered.full_slide is False
    assert rendered.content.startswith(b"\x89PNG")


def test_composite_renderer_can_be_disabled() -> None:
    class RecordingPillow(PillowSlideRenderer):
        def __init__(self) -> None:
            super().__init__(width=320, height=180)
            self.calls = 0

        def render_preview(self, **kwargs: object) -> RenderedSlide:
            self.calls += 1
            return super().render_preview(**kwargs)  # type: ignore[arg-type]

    pillow = RecordingPillow()
    renderer = CompositeSlideRenderer(pillow=pillow, soffice_bin=None, enabled=False)
    renderer.prepare_deck(b"ignored")
    renderer.render_preview(slide_no=2, title="T", body="B")
    assert pillow.calls == 1


def test_fallback_preview_is_not_mislabeled_as_full_slide_render() -> None:
    extracted = ExtractedDocument(
        format_profile="pptx",
        extractor_name="test",
        extractor_version="1",
        blocks=(ExtractedBlock(index_text="Architecture", slide_no=1),),
    )

    # Missing source bytes deterministically exercises the Pillow fallback on hosts
    # both with and without LibreOffice installed.
    prepared = prepare_slide_media(extracted, None)

    assert prepared.media[0].asset_kind == "thumb"
    assert prepared.skipped_media_count == 1
    assert prepared.warnings == ("slide_render_fallback",)


def test_fallback_preview_card_labels_chinese_degraded_preview() -> None:
    rendered = PillowSlideRenderer(width=640, height=360).render_preview(
        slide_no=1,
        title="CRM 三期",
        body="用户操作手册",
    )
    assert rendered.full_slide is False
    # Card must stay a thumb-class fallback (not a faithful full-slide render).
    prepared = prepare_slide_media(
        ExtractedDocument(
            format_profile="pptx",
            extractor_name="test",
            extractor_version="1",
            blocks=(ExtractedBlock(index_text="CRM 三期\n用户操作手册", slide_no=1),),
        ),
        None,
    )
    assert prepared.media[0].asset_kind == "thumb"
