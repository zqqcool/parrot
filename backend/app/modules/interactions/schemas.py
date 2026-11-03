from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class TextInteractionRequest(BaseModel):
    text: str = Field(min_length=1, max_length=12000)


class InteractionAccepted(BaseModel):
    interaction_id: str
    status: str


class InteractionView(BaseModel):
    interaction_id: str
    tenant_id: str
    agent_id: str
    entry_type: str
    input_type: str
    status: str
    runtime_execution_id: str | None = None
    im_channel_id: str | None = None
    im_agent_binding_id: str | None = None
    created_at: datetime
    updated_at: datetime


class InteractionEventView(BaseModel):
    type: str
    event_id: str
    request_id: str
    occurred_at: datetime
    sequence: int
    data: dict[str, object]


class ImEnvelope(BaseModel):
    version: Literal["1"] = "1"
    type: str = Field(min_length=1, max_length=128)
    message_id: str = Field(min_length=1, max_length=128)
    request_id: str = Field(min_length=1, max_length=128)
    interaction_id: str | None = Field(default=None, max_length=64)
    sequence: int | None = Field(default=None, ge=0)
    occurred_at: datetime | None = None
    data: dict[str, object] = Field(default_factory=dict)
