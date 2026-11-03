from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AgentView(BaseModel):
    id: str
    tenant_id: str
    runtime_agent_id: str
    slug: str
    name: str
    description: str
    status: str
    agent_type_key: str
    published: bool
    allow_anonymous: bool
    avatar_present: bool


class AgentAdminView(AgentView):
    """Tenant-admin representation; never expose the prompt on public routes."""

    system_prompt: str
    capability_relevance_threshold: float = Field(ge=0, le=1)


class AgentCreateRequest(BaseModel):
    runtime_agent_id: str = Field(min_length=1, max_length=128)
    slug: str = Field(pattern="^[a-z][a-z0-9-]{2,149}$")
    name: str = Field(min_length=1, max_length=150)
    description: str = Field(default="", max_length=1000)
    system_prompt: str = Field(default="", max_length=20_000)
    agent_type_key: str | None = Field(default=None, min_length=1, max_length=32)
    published: bool = False
    allow_anonymous: bool = False


class AgentUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=1000)
    system_prompt: str | None = Field(default=None, max_length=20_000)
    capability_relevance_threshold: float | None = Field(default=None, ge=0, le=1)
    agent_type_key: str | None = Field(default=None, min_length=1, max_length=32)
    status: str | None = Field(default=None, pattern="^(active|disabled)$")
    published: bool | None = None
    allow_anonymous: bool | None = None


class AgentAvatarUploadRequest(BaseModel):
    content_type: str = Field(min_length=1, max_length=100)
    size_bytes: int = Field(ge=1, le=10 * 1024 * 1024)


class AgentAvatarUploadGrantView(BaseModel):
    object_key: str
    upload_key: str
    upload_token: str
    expires_at: datetime


class AgentAvatarAttachRequest(BaseModel):
    object_key: str = Field(min_length=1, max_length=512)


class AgentLlmBindingsView(BaseModel):
    ids: tuple[str, ...]
    default_id: str | None


class AgentLlmBindingsRequest(BaseModel):
    ids: tuple[str, ...] = Field(min_length=1, max_length=1)
    default_id: str = Field(min_length=1)


class AgentSkillBindingsView(BaseModel):
    ids: tuple[str, ...]


class AgentSkillBindingsRequest(BaseModel):
    ids: tuple[str, ...] = ()


class AgentSkillRecallRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    query: str = Field(min_length=1, max_length=1_000)
    relevance_threshold: float | None = Field(default=None, ge=0, le=1)


class AgentSkillRecallCandidateView(BaseModel):
    id: str
    name: str
    description: str
    version: int
    rank: int
    relevance_score: float | None = Field(default=None, ge=-1, le=1)


class AgentSkillRecallView(BaseModel):
    agent_id: str
    agent_type_key: str
    query: str
    retrieval_method: str
    eligible_skill_count: int
    configured_relevance_threshold: float = Field(ge=0, le=1)
    applied_relevance_threshold: float = Field(ge=0, le=1)
    candidates: tuple[AgentSkillRecallCandidateView, ...]


class AgentMcpToolRecallRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    query: str = Field(min_length=1, max_length=1_000)
    relevance_threshold: float | None = Field(default=None, ge=0, le=1)


class AgentMcpToolRecallCandidateView(BaseModel):
    id: str
    server_id: str
    server_name: str
    name: str
    description: str
    rank: int
    relevance_score: float | None = Field(default=None, ge=-1, le=1)


class AgentMcpToolRecallView(BaseModel):
    agent_id: str
    agent_type_key: str
    query: str
    retrieval_method: str
    eligible_server_count: int
    eligible_tool_count: int
    configured_relevance_threshold: float = Field(ge=0, le=1)
    applied_relevance_threshold: float = Field(ge=0, le=1)
    candidates: tuple[AgentMcpToolRecallCandidateView, ...]


class AgentMcpServerBindingsView(BaseModel):
    ids: tuple[str, ...]


class AgentMcpServerBindingsRequest(BaseModel):
    ids: tuple[str, ...] = ()


class AgentTypeView(BaseModel):
    key: str
    name: str
    description: str
    is_default: bool
    uses_knowledge: bool
    restricts_executable_skills: bool
