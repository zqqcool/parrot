from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class RenderedSlide:
    content: bytes
    content_type: str
    full_slide: bool


class SlideRendererPort(Protocol):
    def render_preview(
        self,
        *,
        slide_no: int,
        title: str,
        body: str,
        embedded: tuple[bytes, ...] = (),
    ) -> RenderedSlide:
        """Return a preview and whether it is a faithful full-slide render."""
        ...
