from __future__ import annotations

import io
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.modules.knowledge.rendering.port import RenderedSlide

# Prefer system CJK-capable fonts so fallback text cards remain readable when
# LibreOffice is unavailable. Order: common macOS, then Linux packaging paths.
# Latin-only fonts (e.g. DejaVu) are intentionally omitted — selecting them would
# regress to tofu boxes for Chinese slide text.
_PREVIEW_FONT_CANDIDATES = (
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansSC-Regular.otf",
    "/usr/share/fonts/opentype/noto/NotoSansSC-Regular.otf",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
)

# Skip tiny decorative embeds (icons/logos) that would steal the preview slot.
_MIN_EMBEDDED_PREVIEW_BYTES = 40_960


class PillowSlideRenderer:
    """Prefer a substantial embedded image; otherwise draw a text card preview."""

    def __init__(self, *, width: int = 1280, height: int = 720) -> None:
        self._width = width
        self._height = height

    def render_preview(
        self,
        *,
        slide_no: int,
        title: str,
        body: str,
        embedded: tuple[bytes, ...] = (),
    ) -> RenderedSlide:
        preview_embed = _select_preview_embed(embedded)
        if preview_embed is not None:
            normalized = _normalize_image(preview_embed, self._width, self._height)
            if normalized is not None:
                return RenderedSlide(normalized, "image/png", full_slide=False)
        return RenderedSlide(
            _text_card(slide_no, title, body, self._width, self._height),
            "image/png",
            full_slide=False,
        )


def _select_preview_embed(embedded: tuple[bytes, ...]) -> bytes | None:
    if not embedded:
        return None
    largest = max(embedded, key=len)
    if len(largest) < _MIN_EMBEDDED_PREVIEW_BYTES:
        return None
    return largest


def _normalize_image(content: bytes, width: int, height: int) -> bytes | None:
    try:
        with Image.open(io.BytesIO(content)) as image:
            converted = image.convert("RGB")
            converted.thumbnail((width, height))
            canvas = Image.new("RGB", (width, height), color=(248, 250, 252))
            offset = ((width - converted.width) // 2, (height - converted.height) // 2)
            canvas.paste(converted, offset)
            return _png_bytes(canvas)
    except Exception:
        return None


def _text_card(slide_no: int, title: str, body: str, width: int, height: int) -> bytes:
    canvas = Image.new("RGB", (width, height), color=(15, 23, 42))
    draw = ImageDraw.Draw(canvas)
    label_font = _preview_font(max(14, height // 36))
    title_font = _preview_font(max(18, height // 28))
    body_font = _preview_font(max(16, height // 32))
    line_gap = max(22, height // 28)
    title_line = _clip_text(title, 80)
    body_lines = _wrap_preview_lines(_body_without_title(body, title_line), max(24, width // 16))
    draw.rectangle((48, 48, width - 48, height - 48), outline=(148, 163, 184), width=2)
    draw.text((72, 72), f"第 {slide_no} 页 · 降级预览", fill=(148, 163, 184), font=label_font)
    draw.text((72, 110), title_line, fill=(248, 250, 252), font=title_font)
    y = 160
    for line in body_lines[:18]:
        draw.text((72, y), line, fill=(203, 213, 225), font=body_font)
        y += line_gap
        if y >= height - 64:
            break
    return _png_bytes(canvas)


@lru_cache(maxsize=8)
def _preview_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _PREVIEW_FONT_CANDIDATES:
        if not Path(path).is_file():
            continue
        try:
            font = ImageFont.truetype(path, size=size)
        except OSError:
            continue
        if _font_supports_cjk(font):
            return font
    return ImageFont.load_default()


def _font_supports_cjk(font: ImageFont.FreeTypeFont | ImageFont.ImageFont) -> bool:
    try:
        left, _top, right, _bottom = font.getbbox("汉")
    except Exception:
        return False
    return right - left >= 8


def _body_without_title(body: str, title: str) -> str:
    text = body.strip()
    heading = title.strip()
    if not text or not heading:
        return _clip_text(text, 900)
    first, _, rest = text.partition("\n")
    if first.strip() == heading:
        return _clip_text(rest.strip(), 900)
    if text.startswith(heading):
        return _clip_text(text[len(heading) :].lstrip("\n").strip(), 900)
    return _clip_text(text, 900)


def _png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def _clip_text(value: str, maximum: int) -> str:
    text = value.strip()
    if len(text) <= maximum:
        return text
    return f"{text[: maximum - 1]}…"


def _wrap_preview_lines(value: str, max_chars: int) -> list[str]:
    """Wrap by character count so CJK lines (often without spaces) stay readable."""
    lines: list[str] = []
    for paragraph in value.replace("\r\n", "\n").split("\n"):
        chunk = paragraph.strip()
        if not chunk:
            continue
        while len(chunk) > max_chars:
            lines.append(chunk[:max_chars])
            chunk = chunk[max_chars:]
        lines.append(chunk)
    return lines or [""]
