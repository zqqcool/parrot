from __future__ import annotations

from dataclasses import replace

from app.modules.knowledge.extraction.types import ExtractedDocument

_EXTENSION_BY_CONTENT_TYPE = {
    "image/gif": ".gif",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
UNSUPPORTED_MEDIA_SKIPPED_WARNING = "unsupported_media_skipped"


def media_file_extension(content_type: str) -> str:
    return _EXTENSION_BY_CONTENT_TYPE.get(_normalized_content_type(content_type), ".bin")


def filter_supported_media(extracted: ExtractedDocument) -> ExtractedDocument:
    supported = tuple(
        item
        for item in extracted.media
        if _normalized_content_type(item.content_type) in _EXTENSION_BY_CONTENT_TYPE
    )
    skipped_count = len(extracted.media) - len(supported)
    if skipped_count == 0:
        return extracted
    warnings = extracted.warnings
    if UNSUPPORTED_MEDIA_SKIPPED_WARNING not in warnings:
        warnings = (*warnings, UNSUPPORTED_MEDIA_SKIPPED_WARNING)
    return replace(
        extracted,
        media=supported,
        skipped_media_count=extracted.skipped_media_count + skipped_count,
        warnings=warnings,
    )


def _normalized_content_type(content_type: str) -> str:
    return content_type.split(";", 1)[0].strip().casefold()
