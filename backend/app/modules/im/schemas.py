from __future__ import annotations

from datetime import datetime
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator


def _validate_origins(origins: tuple[str, ...] | None) -> tuple[str, ...] | None:
    if origins is None:
        return None
    normalized: list[str] = []
    for origin in origins:
        value = origin.strip().rstrip("/")
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.path
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Each allowed origin must be an http(s) origin without a path")
        normalized.append(value)
    if len(set(normalized)) != len(normalized):
        raise ValueError("Allowed origins must not contain duplicates")
    return tuple(normalized)


class ImChannelCreateRequest(BaseModel):
    channel_type: str = Field(default="websocket", min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=128)
    allowed_origins: tuple[str, ...] = Field(min_length=1, max_length=32)

    _validate_allowed_origins = field_validator("allowed_origins")(_validate_origins)


class ImChannelUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    allowed_origins: tuple[str, ...] | None = Field(default=None, min_length=1, max_length=32)
    status: str | None = Field(default=None, pattern="^(enabled|disabled)$")

    _validate_allowed_origins = field_validator("allowed_origins")(_validate_origins)


class ImChannelView(BaseModel):
    id: str
    tenant_id: str
    channel_type: str
    name: str
    public_key: str
    status: str
    allowed_origins: tuple[str, ...]
    created_at: datetime
    updated_at: datetime


class ImChannelTypeView(BaseModel):
    key: str
    label: str
    enabled: bool
    description: str


class PublicImChannelView(BaseModel):
    channel_key: str
    channel_type: str
    name: str


class ImAgentBindingRequest(BaseModel):
    channel_id: str = Field(min_length=1, max_length=64)
    agent_id: str = Field(min_length=1, max_length=64)


class ImAgentBindingView(BaseModel):
    id: str
    tenant_id: str
    channel_id: str
    agent_id: str
    status: str
    channel_name: str
    channel_public_key: str
