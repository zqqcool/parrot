from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.iam.schemas import UserReference


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MemoryCreateRequest(_StrictModel):
    agent_id: str | None = Field(default=None, max_length=64)
    scope_type: Literal["tenant", "agent", "user", "conversation"]
    scope_id: str = Field(min_length=1, max_length=128)
    key: str = Field(min_length=1, max_length=191)
    content: str = Field(min_length=1, max_length=50000)
    memory_type: Literal[
        "user_preference",
        "project_convention",
        "long_term_fact",
        "session_state",
        "conversation_summary",
    ]
    retention_policy: Literal["user_managed", "ttl"] = "user_managed"


class MemoryUpdateRequest(_StrictModel):
    content: str = Field(min_length=1, max_length=50000)
    expected_version: int = Field(ge=1)


class MemoryArchiveRequest(_StrictModel):
    expected_version: int = Field(ge=1)


class MemoryView(BaseModel):
    id: str
    tenant_id: str
    agent_id: str | None
    agent_name: str | None = None
    scope_type: str
    scope_id: str
    key: str
    content: str
    memory_type: str
    retention_policy: str
    status: str
    version: int
    created_by_actor_id: str = Field(validation_alias="created_by_user_id")
    created_by: UserReference | None = None
    created_at: datetime
    updated_at: datetime


class AgentMemorySearchPage(BaseModel):
    items: list[MemoryView]
    total: int = Field(ge=0)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    mode: Literal["browse", "window"] = "browse"
    anchor_id: str | None = None
    retrieval_method: Literal["browse", "hybrid", "lexical", "lexical_fallback"] = "browse"
    degradation_reason: str | None = None
