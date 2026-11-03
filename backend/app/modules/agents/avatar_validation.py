from __future__ import annotations

from app.core.avatar_validation import (
    ValidatedAvatar,
    validate_avatar,
    validate_avatar_upload_metadata,
)

ValidatedAgentAvatar = ValidatedAvatar


def validate_agent_avatar(
    content: bytes,
    declared_content_type: str | None,
    max_bytes: int,
) -> ValidatedAgentAvatar:
    return validate_avatar(content, declared_content_type, max_bytes)


def validate_agent_avatar_upload_metadata(
    declared_content_type: str,
    size_bytes: int,
    max_bytes: int,
) -> None:
    validate_avatar_upload_metadata(declared_content_type, size_bytes, max_bytes)
