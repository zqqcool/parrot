from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.iam.schemas import UserReference
from app.modules.knowledge.chunking import (
    DEFAULT_CHUNK_OVERLAP_CHARS,
    DEFAULT_CHUNK_SEPARATOR,
    DEFAULT_CHUNK_SIZE_CHARS,
    MAX_CHUNK_SIZE_CHARS,
    MIN_CHUNK_SIZE_CHARS,
    decode_chunk_separator,
)
from app.modules.knowledge.runtime_types import KnowledgeMediaRef


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class KnowledgeTextProcessingSettings(_StrictModel):
    normalize_whitespace: bool = False
    remove_urls_and_emails: bool = False


class KnowledgeChunkingSettings(_StrictModel):
    chunk_separator: str = Field(default=DEFAULT_CHUNK_SEPARATOR, min_length=1, max_length=128)
    chunk_size_chars: int = Field(
        default=DEFAULT_CHUNK_SIZE_CHARS,
        ge=MIN_CHUNK_SIZE_CHARS,
        le=MAX_CHUNK_SIZE_CHARS,
    )
    chunk_overlap_chars: int = Field(default=DEFAULT_CHUNK_OVERLAP_CHARS, ge=0)
    text_processing: KnowledgeTextProcessingSettings = Field(
        default_factory=KnowledgeTextProcessingSettings
    )

    @model_validator(mode="after")
    def _overlap_must_fit_within_chunk(self) -> KnowledgeChunkingSettings:
        try:
            decode_chunk_separator(self.chunk_separator)
        except ValueError as error:
            raise ValueError(str(error)) from error
        if self.chunk_overlap_chars >= self.chunk_size_chars:
            raise ValueError("chunk_overlap_chars must be smaller than chunk_size_chars")
        return self


class KnowledgeSpaceCreateRequest(_StrictModel):
    slug: str | None = Field(
        default=None,
        pattern="^[a-z][a-z0-9-]{2,99}$",
        deprecated=True,
        description="Deprecated legacy client field. The server ignores this value.",
    )
    name: str = Field(min_length=1, max_length=150)
    classification: Literal["standard", "restricted"] = "standard"
    chunk_separator: str = Field(default=DEFAULT_CHUNK_SEPARATOR, min_length=1, max_length=128)
    chunk_size_chars: int = Field(
        default=DEFAULT_CHUNK_SIZE_CHARS,
        ge=MIN_CHUNK_SIZE_CHARS,
        le=MAX_CHUNK_SIZE_CHARS,
    )
    chunk_overlap_chars: int = Field(default=DEFAULT_CHUNK_OVERLAP_CHARS, ge=0)
    embedding_config_id: str | None = Field(default=None, max_length=64)
    text_processing: KnowledgeTextProcessingSettings = Field(
        default_factory=KnowledgeTextProcessingSettings
    )

    @model_validator(mode="after")
    def _overlap_must_fit_within_chunk(self) -> KnowledgeSpaceCreateRequest:
        try:
            decode_chunk_separator(self.chunk_separator)
        except ValueError as error:
            raise ValueError(str(error)) from error
        if self.chunk_overlap_chars >= self.chunk_size_chars:
            raise ValueError("chunk_overlap_chars must be smaller than chunk_size_chars")
        return self


class KnowledgeSpaceChunkingUpdateRequest(KnowledgeChunkingSettings):
    pass


class KnowledgeSpaceRetrievalUpdateRequest(_StrictModel):
    embedding_config_id: str | None = Field(default=None, max_length=64)
    candidate_top_k: int = Field(default=20, ge=1, le=60)
    min_vector_score: float | None = Field(default=None, ge=0, le=1)
    rerank_enabled: bool = False
    reranker_config_id: str | None = Field(default=None, max_length=64)
    rerank_top_n: int = Field(default=10, ge=1, le=60)
    min_rerank_score: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def validate_dependencies(self) -> KnowledgeSpaceRetrievalUpdateRequest:
        if self.embedding_config_id is None:
            if (
                self.rerank_enabled
                or self.reranker_config_id is not None
                or self.min_vector_score is not None
            ):
                raise ValueError("reranking requires an embedding_config_id")
            return self
        if self.rerank_enabled and self.reranker_config_id is None:
            raise ValueError("reranking requires a reranker_config_id")
        if not self.rerank_enabled and self.reranker_config_id is not None:
            raise ValueError("reranker_config_id requires rerank_enabled")
        if self.rerank_enabled and self.rerank_top_n > self.candidate_top_k:
            raise ValueError("rerank_top_n must not exceed candidate_top_k")
        return self


class KnowledgeSpaceView(BaseModel):
    id: str
    tenant_id: str
    slug: str
    name: str
    classification: str
    status: str
    chunk_separator: str
    chunk_size_chars: int
    chunk_overlap_chars: int
    text_processing: KnowledgeTextProcessingSettings = Field(
        default_factory=KnowledgeTextProcessingSettings
    )
    embedding_config_id: str | None
    embedding_config_provider: str | None
    embedding_config_model: str | None
    embedding_config_base_url: str | None
    embedding_config_dimension: int | None
    embedding_config_version: int | None
    candidate_top_k: int
    min_vector_score: float | None
    rerank_enabled: bool
    reranker_config_id: str | None
    rerank_top_n: int
    min_rerank_score: float | None
    retrieval_index_revision: int
    retrieval_index_status: str
    access_revision: int
    created_at: datetime
    updated_at: datetime


class KnowledgeSpaceGrantsRequest(_StrictModel):
    user_ids: tuple[str, ...] = Field(default=(), max_length=500)
    group_ids: tuple[str, ...] = Field(default=(), max_length=500)


class KnowledgeSpaceGrantsView(BaseModel):
    user_ids: tuple[str, ...]
    group_ids: tuple[str, ...]
    access_revision: int


class KnowledgeDocumentCreateRequest(_StrictModel):
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1, max_length=200000)
    source_uri: str | None = Field(default=None, max_length=1000)


class KnowledgeDocumentTextVersionCreateRequest(_StrictModel):
    content: str = Field(min_length=1, max_length=200000)


class KnowledgeDocumentView(BaseModel):
    id: str
    tenant_id: str
    space_id: str
    title: str
    source_uri: str | None
    status: str
    current_version: int
    chunk_count: int
    changed_by_display_name: str
    changed_by_user: UserReference | None
    created_at: datetime
    updated_at: datetime


class KnowledgeSourceActivityView(BaseModel):
    id: str
    title: str
    original_filename: str
    content_type: str
    size_bytes: int
    change_kind: Literal["create", "replace"]
    status: str
    document_id: str | None
    attempts: int
    error_code: str | None
    created_by_display_name: str
    created_by_user: UserReference | None
    staging_expires_at: datetime | None
    created_at: datetime
    updated_at: datetime


class KnowledgeSourceActivityPageView(BaseModel):
    items: tuple[KnowledgeSourceActivityView, ...]
    page: int
    page_size: int
    total: int


class KnowledgeDocumentVersionView(BaseModel):
    id: str
    document_id: str
    source_id: str | None
    version: int
    status: str
    extraction_status: str
    chunk_separator: str
    chunk_size_chars: int
    chunk_overlap_chars: int
    text_processing: KnowledgeTextProcessingSettings = Field(
        default_factory=KnowledgeTextProcessingSettings
    )
    format_profile: str = "plain_text"
    slide_count: int = 0
    sheet_count: int = 0
    section_count: int = 0
    media_count: int = 0
    skipped_media_count: int = 0
    published_at: datetime | None
    created_at: datetime


class KnowledgeDocumentChunkView(BaseModel):
    id: str
    ordinal: int
    citation_anchor: str
    content: str
    content_chars: int


class KnowledgeDocumentChunkPageView(BaseModel):
    items: tuple[KnowledgeDocumentChunkView, ...]
    page: int
    page_size: int
    total: int


class KnowledgeSourceUploadRequest(_StrictModel):
    title: str = Field(min_length=1, max_length=300)
    filename: str = Field(min_length=1, max_length=300)
    content_type: str = Field(min_length=1, max_length=128)
    size_bytes: int = Field(ge=1)


class KnowledgeDocumentVersionUploadRequest(_StrictModel):
    filename: str = Field(min_length=1, max_length=300)
    content_type: str = Field(min_length=1, max_length=128)
    size_bytes: int = Field(ge=1)


class KnowledgeSourceUploadGrantView(BaseModel):
    source_id: str
    object_key: str
    upload_key: str
    upload_token: str
    expires_at: datetime


class KnowledgeSourceConfirmRequest(_StrictModel):
    staging_key: str = Field(min_length=1, max_length=512)


class KnowledgeIngestionView(BaseModel):
    id: str
    title: str
    source_id: str
    document_id: str
    document_version_id: str
    status: str
    attempts: int
    error_code: str | None
    created_at: datetime
    updated_at: datetime


class KnowledgeMediaRefView(BaseModel):
    asset_id: str
    slide_no: int | None = None
    sheet_name: str | None = None
    cell_anchor: str | None = None
    section_path: str | None = None
    asset_kind: str = "slide_render"
    ordinal: int = 0


def knowledge_media_ref_view(item: KnowledgeMediaRef) -> KnowledgeMediaRefView:
    return KnowledgeMediaRefView.model_validate(item, from_attributes=True)


class KnowledgeSearchResult(BaseModel):
    chunk_id: str
    document_id: str
    document_version_id: str
    title: str
    citation_anchor: str
    content_chars: int
    score: float
    excerpt: str
    excerpt_truncated: bool
    retrieval_method: str
    embedding_config_name: str | None = None
    reranker_config_name: str | None = None
    degradation_reason: str | None = None
    match_sources: tuple[Literal["lexical", "vector"], ...] = ()
    vector_score: float | None = None
    slide_no: int | None = None
    media_refs: tuple[KnowledgeMediaRefView, ...] = ()


class KnowledgeCitationView(BaseModel):
    citation_id: str
    document_id: str
    document_version_id: str
    title: str
    citation_anchor: str
    excerpt: str
    content_chars: int
    content: str
    slide_no: int | None = None
    media_refs: tuple[KnowledgeMediaRefView, ...] = ()


class AgentKnowledgeSpaceBindingsRequest(_StrictModel):
    space_ids: tuple[str, ...] = Field(default=(), max_length=100)


class AgentKnowledgeSpaceBindingsView(BaseModel):
    space_ids: tuple[str, ...]


class KnowledgeSpaceAgentBindingsView(BaseModel):
    agent_ids: tuple[str, ...]


class AgentKnowledgeSearchTestRequest(_StrictModel):
    query: str = Field(min_length=1, max_length=1_000)
    limit: int = Field(default=6, ge=1, le=12)


class AgentKnowledgeSearchTestItem(BaseModel):
    citation_id: str
    title: str
    citation_anchor: str
    space_id: str
    retrieval_method: str
    score: float
    excerpt: str
    embedding_config_name: str | None
    reranker_config_name: str | None
    degradation_reason: str | None
    match_sources: tuple[Literal["lexical", "vector"], ...] = ()
    vector_score: float | None = None
    slide_no: int | None = None
    media_refs: tuple[KnowledgeMediaRefView, ...] = ()


class AgentKnowledgeSearchTestView(BaseModel):
    status: str
    retrieval_method: str
    candidate_count: int
    duration_ms: int
    degradation_reasons: tuple[str, ...]
    items: tuple[AgentKnowledgeSearchTestItem, ...]
