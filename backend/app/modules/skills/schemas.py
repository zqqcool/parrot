from datetime import datetime

from pydantic import BaseModel, Field

from app.modules.iam.schemas import UserReference


class SkillBoundAgentView(BaseModel):
    id: str
    name: str


class SkillView(BaseModel):
    id: str
    tenant_id: str
    created_by_user: UserReference | None = None
    name: str
    description: str
    status: str
    version: int
    manifest: dict[str, object]
    instructions: str
    package_filename: str | None = None
    package_size_bytes: int | None = None
    package_sha256: str | None = None
    current_version_id: str | None = None
    draft_version_id: str | None = None
    has_draft: bool = False
    build_status: str | None = None
    build_source_checksum: str | None = None
    bound_agents: tuple[SkillBoundAgentView, ...] | None = None


class SkillVersionView(BaseModel):
    id: str
    tenant_id: str
    skill_id: str
    version: int
    status: str
    description: str
    manifest: dict[str, object]
    instructions: str
    package_filename: str | None = None
    package_size_bytes: int | None = None
    package_sha256: str | None = None
    source_version_id: str | None = None
    created_by_user: UserReference | None = None
    published_by_user: UserReference | None = None
    published_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    build_status: str | None = None
    build_source_checksum: str | None = None
    runtime_artifact_sha256: str | None = None
    runtime_artifact_size_bytes: int | None = None


class SkillBuildView(BaseModel):
    id: str
    source_checksum: str
    status: str
    error_code: str | None = None
    failure_message: str | None = None
    artifact_sha256: str | None = None
    artifact_size_bytes: int | None = None
    created_at: datetime
    updated_at: datetime


class SkillFileView(BaseModel):
    path: str
    size_bytes: int
    editable: bool
    kind: str = "file"


class SkillFileContentView(SkillFileView):
    content: str
    checksum: str


class SkillDraftForkRequest(BaseModel):
    source_version_id: str | None = None


class SkillRollbackRequest(BaseModel):
    version_id: str = Field(min_length=1, max_length=64)


class SkillDraftFileWriteRequest(BaseModel):
    content: str = Field(max_length=1_000_000)
    expected_checksum: str = Field(min_length=1, max_length=64)


class SkillDraftFileCreateRequest(BaseModel):
    path: str = Field(min_length=1, max_length=512)
    content: str = Field(default="", max_length=1_000_000)
    expected_checksum: str = Field(min_length=1, max_length=64)


class SkillDraftDirectoryCreateRequest(BaseModel):
    path: str = Field(min_length=1, max_length=512)
    expected_checksum: str = Field(min_length=1, max_length=64)


class SkillDraftEntryDeleteRequest(BaseModel):
    path: str = Field(min_length=1, max_length=512)
    expected_checksum: str = Field(min_length=1, max_length=64)


class SkillDraftEntryMutationView(BaseModel):
    path: str
    checksum: str


class SkillCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=2000)
    manifest: dict[str, object] = Field(default_factory=dict)
    instructions: str = Field(default="", max_length=100_000)


class SkillUpdateRequest(BaseModel):
    description: str | None = Field(default=None, max_length=2000)
    manifest: dict[str, object] | None = None
    instructions: str | None = Field(default=None, max_length=100_000)
    status: str | None = Field(default=None, pattern="^(draft|published|disabled)$")
