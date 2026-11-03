from __future__ import annotations

import io
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest
from PIL import Image
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.object_storage import ObjectStoragePort
from app.infrastructure.db.session import DatabaseManager
from app.modules.iam.schemas import PrincipalContext
from app.modules.knowledge.lifecycle_service import KnowledgeDocumentLifecycleService
from app.modules.knowledge.media_models import KnowledgeMediaAsset
from app.modules.knowledge.media_repository import KnowledgeMediaRepository
from app.modules.knowledge.models import KnowledgeChunk
from app.modules.knowledge.rendering.pillow_slide_renderer import PillowSlideRenderer
from app.modules.knowledge.repository import KnowledgeRepository


def principal(*permissions: str) -> PrincipalContext:
    return PrincipalContext(
        tenant_id="tenant_test",
        subject_id="user_test",
        username="operator",
        display_name="Operator",
        permissions=permissions,
        tenants=(),
        must_change_password=False,
        request_id="req_test",
    )


def test_pillow_slide_renderer_draws_text_card_without_embedded_images() -> None:
    rendered = PillowSlideRenderer(width=640, height=360).render_preview(
        slide_no=3,
        title="Architecture",
        body="S3 object storage overview",
    )
    assert rendered.content_type == "image/png"
    assert rendered.full_slide is False
    with Image.open(io.BytesIO(rendered.content)) as image:
        assert image.size == (640, 360)


def test_pillow_text_card_wraps_cjk_paragraphs_and_uses_system_font_when_present() -> None:
    from pathlib import Path

    from app.modules.knowledge.rendering.pillow_slide_renderer import (
        _PREVIEW_FONT_CANDIDATES,
        _body_without_title,
        _preview_font,
        _wrap_preview_lines,
    )

    assert _wrap_preview_lines("CRM 三期\n用户操作手册 – 中文版", 80) == [
        "CRM 三期",
        "用户操作手册 – 中文版",
    ]
    assert _body_without_title("CRM 三期\n用户操作手册", "CRM 三期") == "用户操作手册"
    rendered = PillowSlideRenderer(width=640, height=360).render_preview(
        slide_no=1,
        title="2024.5",
        body="2024.5\nCRM 三期\n用户操作手册 – 中文版",
    )
    assert rendered.full_slide is False
    assert rendered.content.startswith(b"\x89PNG")
    if any(Path(path).is_file() for path in _PREVIEW_FONT_CANDIDATES):
        font = _preview_font(24)
        left, _top, right, _bottom = font.getbbox("操")
        assert right - left > 4


def test_pillow_slide_renderer_prefers_largest_embedded_image() -> None:
    tiny = Image.new("RGB", (8, 8), color=(255, 0, 0))
    large = Image.new("RGB", (640, 360), color=(0, 255, 0))
    tiny_buf = io.BytesIO()
    large_buf = io.BytesIO()
    tiny.save(tiny_buf, format="PNG")
    large.save(large_buf, format="PNG", optimize=False)
    # Ensure the preferred embed clears the decorative-image size floor.
    while len(large_buf.getvalue()) < 41_000:
        large = Image.new("RGB", (large.size[0] + 64, large.size[1] + 36), color=(0, 255, 0))
        large_buf = io.BytesIO()
        large.save(large_buf, format="PNG", optimize=False)
    rendered = PillowSlideRenderer(width=320, height=180).render_preview(
        slide_no=1,
        title="Ignored",
        body="Ignored",
        embedded=(tiny_buf.getvalue(), large_buf.getvalue()),
    )
    assert rendered.content_type == "image/png"
    assert rendered.full_slide is False
    assert len(rendered.content) > 0


def test_pillow_slide_renderer_skips_tiny_embedded_images_for_text_card() -> None:
    tiny = Image.new("RGB", (16, 16), color=(255, 0, 0))
    tiny_buf = io.BytesIO()
    tiny.save(tiny_buf, format="PNG")
    rendered = PillowSlideRenderer(width=640, height=360).render_preview(
        slide_no=1,
        title="CRM 三期",
        body="CRM 三期\n用户操作手册",
        embedded=(tiny_buf.getvalue(),),
    )
    assert rendered.full_slide is False
    # Text-card fallback is much smaller than a normalized screenshot canvas.
    assert len(rendered.content) < 30_000


@pytest.mark.asyncio
async def test_media_file_download_is_space_authorized() -> None:
    asset = SimpleNamespace(
        id="media_test",
        space_id="space_test",
        slide_no=2,
        asset_kind="slide_render",
        content_type="image/png",
        object_key="tenant/media.png",
        status="ready",
    )
    session = SimpleNamespace(scalar=AsyncMock(return_value=asset), add=Mock())
    storage = SimpleNamespace(read=AsyncMock(return_value=SimpleNamespace(content=b"png-bytes")))
    instance = KnowledgeDocumentLifecycleService(
        cast(AsyncSession, session),
        cast(DatabaseManager, SimpleNamespace(set_tenant=AsyncMock())),
        object_storage=cast(ObjectStoragePort, storage),
    )
    instance.repository = cast(
        KnowledgeRepository,
        SimpleNamespace(
            get_space=AsyncMock(return_value=SimpleNamespace(id="space_test", status="active")),
            user_has_access=AsyncMock(return_value=True),
        ),
    )
    instance.media = cast(
        KnowledgeMediaRepository, SimpleNamespace(downloadable=AsyncMock(return_value=asset))
    )

    result = await instance.media_file(
        principal("knowledge.documents.read"), "tenant_test", asset.id
    )

    assert result.content == b"png-bytes"
    assert result.content_type == "image/png"
    assert result.filename.startswith("slide_render-2")
    session.add.assert_called_once()


@pytest.mark.asyncio
async def test_media_file_hides_assets_without_space_access() -> None:
    asset = SimpleNamespace(
        id="media_test",
        space_id="space_test",
        slide_no=2,
        asset_kind="slide_render",
        content_type="image/png",
        object_key="tenant/media.png",
        status="ready",
    )
    instance = KnowledgeDocumentLifecycleService(
        cast(AsyncSession, SimpleNamespace(scalar=AsyncMock(return_value=asset), add=Mock())),
        cast(DatabaseManager, SimpleNamespace(set_tenant=AsyncMock())),
        object_storage=cast(ObjectStoragePort, SimpleNamespace(read=AsyncMock())),
    )
    instance.repository = cast(
        KnowledgeRepository,
        SimpleNamespace(
            get_space=AsyncMock(return_value=SimpleNamespace(id="space_test", status="active")),
            user_has_access=AsyncMock(return_value=False),
        ),
    )
    instance.media = cast(
        KnowledgeMediaRepository, SimpleNamespace(downloadable=AsyncMock(return_value=asset))
    )

    with pytest.raises(AppError) as error:
        await instance.media_file(principal("knowledge.documents.read"), "tenant_test", asset.id)
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_media_file_hides_asset_when_document_version_is_not_downloadable() -> None:
    instance = KnowledgeDocumentLifecycleService(
        cast(AsyncSession, SimpleNamespace(add=Mock())),
        cast(DatabaseManager, SimpleNamespace(set_tenant=AsyncMock())),
        object_storage=cast(ObjectStoragePort, SimpleNamespace(read=AsyncMock())),
    )
    instance.media = cast(
        KnowledgeMediaRepository, SimpleNamespace(downloadable=AsyncMock(return_value=None))
    )

    with pytest.raises(AppError) as error:
        await instance.media_file(
            principal("knowledge.documents.read"), "tenant_test", "media_archived"
        )

    assert error.value.status_code == 404


def test_content_disposition_prefers_ascii_filename() -> None:
    from app.api.routes.admin_knowledge_documents import content_disposition

    assert (
        content_disposition("inline", "slide_render-122.png")
        == 'inline; filename="slide_render-122.png"'
    )
    assert content_disposition("attachment", "报告.png").startswith("attachment; filename*=UTF-8''")


def test_group_foreign_keys_do_not_null_the_non_nullable_tenant_column() -> None:
    tables = (
        cast(Table, KnowledgeChunk.__table__),
        cast(Table, KnowledgeMediaAsset.__table__),
    )
    for table in tables:
        group_constraint = next(
            constraint
            for constraint in table.foreign_key_constraints
            if any(
                element.target_fullname == "knowledge_evidence_groups.id"
                for element in constraint.elements
            )
        )

        assert group_constraint.ondelete == "CASCADE"
