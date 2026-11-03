from __future__ import annotations

from pydantic import BaseModel, Field


class TenantView(BaseModel):
    id: str
    slug: str
    name: str
    status: str


class TenantCreateRequest(BaseModel):
    slug: str = Field(pattern="^[a-z][a-z0-9-]{2,99}$")
    name: str = Field(min_length=1, max_length=150)


class GroupView(BaseModel):
    id: str
    name: str
    description: str
    status: str
    is_system: bool
    member_count: int = 0


class GroupCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    description: str = Field(default="", max_length=512)


class AssignmentRequest(BaseModel):
    ids: tuple[str, ...]


class AssignmentView(BaseModel):
    ids: tuple[str, ...]
