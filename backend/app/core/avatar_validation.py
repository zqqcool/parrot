from __future__ import annotations

import warnings
from dataclasses import dataclass
from io import BytesIO

from PIL import Image, UnidentifiedImageError
from PIL.Image import DecompressionBombError, DecompressionBombWarning
from starlette import status

from app.core.errors import AppError

MAX_AVATAR_DIMENSION = 4096
MAX_AVATAR_PIXELS = MAX_AVATAR_DIMENSION * MAX_AVATAR_DIMENSION

_FORMATS = {
    "JPEG": ("image/jpeg", "jpg"),
    "PNG": ("image/png", "png"),
    "WEBP": ("image/webp", "webp"),
}
_CONTENT_TYPES = {details[0] for details in _FORMATS.values()}


@dataclass(frozen=True)
class ValidatedAvatar:
    content: bytes
    content_type: str
    extension: str


def validate_avatar(
    content: bytes,
    declared_content_type: str | None,
    max_bytes: int,
) -> ValidatedAvatar:
    if not content:
        raise AppError(
            "AVATAR_EMPTY",
            "Avatar file is empty",
            status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    if len(content) > max_bytes:
        raise AppError(
            "AVATAR_TOO_LARGE",
            f"Avatar file must not exceed {max_bytes} bytes",
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        )
    image_format, width, height = _inspect_image(content)
    format_details = _FORMATS.get(image_format)
    if format_details is None or declared_content_type != format_details[0]:
        raise AppError(
            "AVATAR_TYPE_INVALID",
            "Avatar must be a PNG, JPEG, or WebP image",
            status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    if width > MAX_AVATAR_DIMENSION or height > MAX_AVATAR_DIMENSION:
        raise AppError(
            "AVATAR_DIMENSIONS_INVALID",
            "Avatar dimensions must not exceed 4096 pixels",
            status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    if width * height > MAX_AVATAR_PIXELS:
        raise AppError(
            "AVATAR_DIMENSIONS_INVALID",
            "Avatar contains too many pixels",
            status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    content_type, extension = format_details
    return ValidatedAvatar(content=content, content_type=content_type, extension=extension)


def validate_avatar_upload_metadata(
    declared_content_type: str,
    size_bytes: int,
    max_bytes: int,
) -> None:
    if declared_content_type not in _CONTENT_TYPES:
        raise AppError(
            "AVATAR_TYPE_INVALID",
            "Avatar must be a PNG, JPEG, or WebP image",
            status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    if size_bytes < 1:
        raise AppError(
            "AVATAR_EMPTY",
            "Avatar file is empty",
            status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    if size_bytes > max_bytes:
        raise AppError(
            "AVATAR_TOO_LARGE",
            f"Avatar file must not exceed {max_bytes} bytes",
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        )


def _inspect_image(content: bytes) -> tuple[str, int, int]:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", DecompressionBombWarning)
            with Image.open(BytesIO(content)) as image:
                image.verify()
            with Image.open(BytesIO(content)) as image:
                width, height = image.size
                return str(image.format or ""), width, height
    except (
        DecompressionBombError,
        DecompressionBombWarning,
        OSError,
        UnidentifiedImageError,
    ) as exc:
        raise AppError(
            "AVATAR_TYPE_INVALID",
            "Avatar must be a valid PNG, JPEG, or WebP image",
            status.HTTP_422_UNPROCESSABLE_CONTENT,
        ) from exc
