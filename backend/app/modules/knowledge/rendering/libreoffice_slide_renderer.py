from __future__ import annotations

import io
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from app.modules.knowledge.rendering.pillow_slide_renderer import PillowSlideRenderer
from app.modules.knowledge.rendering.port import RenderedSlide, SlideRendererPort

logger = logging.getLogger(__name__)


class CompositeSlideRenderer:
    """Prefer LibreOffice deck renders; fall back to Pillow text/embedded previews."""

    def __init__(
        self,
        *,
        pillow: SlideRendererPort | None = None,
        soffice_bin: str | None = None,
        enabled: bool = True,
    ) -> None:
        self._pillow = pillow or PillowSlideRenderer()
        self._soffice = soffice_bin or shutil.which("soffice") or shutil.which("libreoffice")
        self._enabled = enabled
        self._deck_cache: dict[int, RenderedSlide] | None = None

    def prepare_deck(self, source_bytes: bytes | None) -> None:
        self._deck_cache = None
        if not self._enabled or not source_bytes or self._soffice is None:
            return
        try:
            self._deck_cache = _render_pptx_via_libreoffice(source_bytes, self._soffice)
        except Exception:
            logger.exception("LibreOffice slide render failed; using Pillow fallback")
            self._deck_cache = None

    def render_preview(
        self,
        *,
        slide_no: int,
        title: str,
        body: str,
        embedded: tuple[bytes, ...] = (),
    ) -> RenderedSlide:
        if self._deck_cache and slide_no in self._deck_cache:
            return self._deck_cache[slide_no]
        return self._pillow.render_preview(
            slide_no=slide_no,
            title=title,
            body=body,
            embedded=embedded,
        )


def _render_pptx_via_libreoffice(source_bytes: bytes, soffice_bin: str) -> dict[int, RenderedSlide]:
    import pypdfium2 as pdfium  # type: ignore[import-untyped]

    with tempfile.TemporaryDirectory(prefix="parrot-pptx-render-") as tmp:
        root = Path(tmp)
        pptx_path = root / "deck.pptx"
        pptx_path.write_bytes(source_bytes)
        completed = subprocess.run(
            [
                soffice_bin,
                "--headless",
                "--nologo",
                "--nofirststartwizard",
                "--convert-to",
                "pdf",
                "--outdir",
                str(root),
                str(pptx_path),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr or completed.stdout or "soffice failed")
        pdf_path = root / "deck.pdf"
        if not pdf_path.exists():
            raise RuntimeError("LibreOffice did not produce a PDF")
        document = pdfium.PdfDocument(pdf_path.read_bytes())
        rendered: dict[int, RenderedSlide] = {}
        for index in range(len(document)):
            page: Any = document[index]
            bitmap: Any = page.render(scale=2)
            image: Any = bitmap.to_pil()
            buffer = io.BytesIO()
            image.save(buffer, format="PNG", optimize=True)
            rendered[index + 1] = RenderedSlide(buffer.getvalue(), "image/png", full_slide=True)
        return rendered
