from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base, TimestampMixin


class KnowledgeSpace(Base, TimestampMixin):
    __tablename__ = "knowledge_spaces"
    __table_args__ = (
        UniqueConstraint("tenant_id", "slug", name="uq_knowledge_space_tenant_slug"),
        UniqueConstraint("tenant_id", "id", name="uq_knowledge_space_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "embedding_config_id"],
            ["embedding_configs.tenant_id", "embedding_configs.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "reranker_config_id"],
            ["reranker_configs.tenant_id", "reranker_configs.id"],
            ondelete="RESTRICT",
        ),
        Index("ix_knowledge_space_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    classification: Mapped[str] = mapped_column(String(32), default="standard", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    chunk_separator: Mapped[str] = mapped_column(String(128), default=r"\n\n", nullable=False)
    chunk_size_chars: Mapped[int] = mapped_column(Integer, default=4_000, nullable=False)
    chunk_overlap_chars: Mapped[int] = mapped_column(Integer, default=200, nullable=False)
    normalize_whitespace: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    remove_urls_and_emails: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    embedding_config_id: Mapped[str | None] = mapped_column(String(64))
    embedding_config_provider: Mapped[str | None] = mapped_column(String(64))
    embedding_config_model: Mapped[str | None] = mapped_column(String(128))
    embedding_config_base_url: Mapped[str | None] = mapped_column(String(512))
    embedding_config_dimension: Mapped[int | None] = mapped_column(Integer)
    embedding_config_version: Mapped[int | None] = mapped_column(Integer)
    candidate_top_k: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    min_vector_score: Mapped[float | None] = mapped_column(Float)
    rerank_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reranker_config_id: Mapped[str | None] = mapped_column(String(64))
    rerank_top_n: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    min_rerank_score: Mapped[float | None] = mapped_column(Float)
    retrieval_index_revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    retrieval_index_status: Mapped[str] = mapped_column(
        String(32), default="not_configured", nullable=False
    )
    access_revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_by_user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )


class KnowledgeSpaceUserGrant(Base, TimestampMixin):
    __tablename__ = "knowledge_space_user_grants"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "space_id"],
            ["knowledge_spaces.tenant_id", "knowledge_spaces.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("tenant_id", "space_id", "user_id", name="uq_knowledge_space_user_grant"),
        Index("ix_knowledge_user_grant_lookup", "tenant_id", "user_id", "space_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    space_id: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )


class KnowledgeSpaceGroupGrant(Base, TimestampMixin):
    __tablename__ = "knowledge_space_group_grants"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "space_id"],
            ["knowledge_spaces.tenant_id", "knowledge_spaces.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "group_id"], ["groups.tenant_id", "groups.id"], ondelete="CASCADE"
        ),
        UniqueConstraint(
            "tenant_id", "space_id", "group_id", name="uq_knowledge_space_group_grant"
        ),
        Index("ix_knowledge_group_grant_lookup", "tenant_id", "group_id", "space_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    space_id: Mapped[str] = mapped_column(String(64), nullable=False)
    group_id: Mapped[str] = mapped_column(String(64), nullable=False)


class KnowledgeDocument(Base, TimestampMixin):
    __tablename__ = "knowledge_documents"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_knowledge_document_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "space_id"],
            ["knowledge_spaces.tenant_id", "knowledge_spaces.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "source_id"],
            ["knowledge_sources.tenant_id", "knowledge_sources.id"],
            name="fk_knowledge_document_source",
            ondelete="RESTRICT",
            use_alter=True,
        ),
        Index("ix_knowledge_document_space_status", "tenant_id", "space_id", "status"),
        Index(
            "uq_knowledge_document_available_title",
            "tenant_id",
            "space_id",
            "title_key",
            unique=True,
            postgresql_where="status IN ('active', 'processing')",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    space_id: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    title_key: Mapped[str] = mapped_column(String(300), nullable=False)
    source_uri: Mapped[str | None] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    created_by_user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    source_id: Mapped[str | None] = mapped_column(String(64))


class KnowledgeSource(Base, TimestampMixin):
    __tablename__ = "knowledge_sources"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_knowledge_source_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "space_id"],
            ["knowledge_spaces.tenant_id", "knowledge_spaces.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "target_document_id"],
            ["knowledge_documents.tenant_id", "knowledge_documents.id"],
            ondelete="RESTRICT",
        ),
        Index("ix_knowledge_source_space_status", "tenant_id", "space_id", "status"),
        Index("ix_knowledge_source_staging_cleanup", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    space_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(300), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    declared_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    content_sha256: Mapped[str | None] = mapped_column(String(64))
    staging_key: Mapped[str | None] = mapped_column(String(512))
    object_key: Mapped[str | None] = mapped_column(String(512))
    target_document_id: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="staging", nullable=False)
    created_by_user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )


class KnowledgeDocumentVersion(Base, TimestampMixin):
    __tablename__ = "knowledge_document_versions"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "document_id", "version", name="uq_knowledge_document_version"
        ),
        UniqueConstraint("tenant_id", "id", name="uq_knowledge_document_version_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["knowledge_documents.tenant_id", "knowledge_documents.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "source_id"],
            ["knowledge_sources.tenant_id", "knowledge_sources.id"],
            ondelete="RESTRICT",
        ),
        Index("ix_knowledge_version_document_status", "tenant_id", "document_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    document_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[str | None] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), default="published", nullable=False)
    extraction_status: Mapped[str] = mapped_column(String(32), default="completed", nullable=False)
    chunk_separator: Mapped[str] = mapped_column(String(128), default=r"\n\n", nullable=False)
    chunk_size_chars: Mapped[int] = mapped_column(Integer, default=4_000, nullable=False)
    chunk_overlap_chars: Mapped[int] = mapped_column(Integer, default=200, nullable=False)
    normalize_whitespace: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    remove_urls_and_emails: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    format_profile: Mapped[str] = mapped_column(String(32), default="plain_text", nullable=False)
    extractor_name: Mapped[str | None] = mapped_column(String(64))
    extractor_version: Mapped[str | None] = mapped_column(String(32))
    slide_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sheet_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    section_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    media_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    skipped_media_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class KnowledgeChunk(Base, TimestampMixin):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_knowledge_chunk_tenant_id"),
        UniqueConstraint(
            "tenant_id", "document_version_id", "ordinal", name="uq_knowledge_chunk_ordinal"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "space_id"],
            ["knowledge_spaces.tenant_id", "knowledge_spaces.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "document_version_id"],
            ["knowledge_document_versions.tenant_id", "knowledge_document_versions.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "group_id"],
            ["knowledge_evidence_groups.tenant_id", "knowledge_evidence_groups.id"],
            ondelete="CASCADE",
        ),
        Index("ix_knowledge_chunk_space_version", "tenant_id", "space_id", "document_version_id"),
        Index("ix_knowledge_chunk_group", "tenant_id", "group_id", "ordinal"),
        Index("ix_knowledge_chunk_slide", "tenant_id", "document_version_id", "slide_no"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    space_id: Mapped[str] = mapped_column(String(64), nullable=False)
    document_version_id: Mapped[str] = mapped_column(String(64), nullable=False)
    group_id: Mapped[str | None] = mapped_column(String(64))
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    citation_anchor: Mapped[str] = mapped_column(String(191), nullable=False)
    format_profile: Mapped[str] = mapped_column(String(32), default="plain_text", nullable=False)
    block_kind: Mapped[str | None] = mapped_column(String(32))
    page_kind: Mapped[str | None] = mapped_column(String(32))
    slide_no: Mapped[int | None] = mapped_column(Integer)
    sheet_name: Mapped[str | None] = mapped_column(String(191))
    section_path: Mapped[str | None] = mapped_column(String(512))
    step_label: Mapped[str | None] = mapped_column(String(191))
    cell_anchor: Mapped[str | None] = mapped_column(String(64))
    search_vector: Mapped[object] = mapped_column(TSVECTOR, nullable=False)


class AgentKnowledgeSpaceBinding(Base, TimestampMixin):
    __tablename__ = "agent_knowledge_space_bindings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "agent_id"],
            ["agent_publications.tenant_id", "agent_publications.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "space_id"],
            ["knowledge_spaces.tenant_id", "knowledge_spaces.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("tenant_id", "agent_id", "space_id", name="uq_agent_knowledge_space"),
        Index("ix_agent_knowledge_space_lookup", "tenant_id", "agent_id", "space_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(64), nullable=False)
    space_id: Mapped[str] = mapped_column(String(64), nullable=False)


class KnowledgeIngestionJob(Base, TimestampMixin):
    __tablename__ = "knowledge_ingestion_jobs"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "source_id",
            "document_version_id",
            "action",
            name="uq_knowledge_ingestion_job_version",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "source_id"],
            ["knowledge_sources.tenant_id", "knowledge_sources.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "document_version_id"],
            ["knowledge_document_versions.tenant_id", "knowledge_document_versions.id"],
            ondelete="CASCADE",
        ),
        Index(
            "ix_knowledge_ingestion_job_claim",
            "tenant_id",
            "status",
            "lease_until",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    document_version_id: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(32), default="extract", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="queued", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lease_owner: Mapped[str | None] = mapped_column(String(128))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(128))


class KnowledgeVectorIndexJob(Base, TimestampMixin):
    __tablename__ = "knowledge_vector_index_jobs"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "document_version_id",
            "embedding_config_id",
            "index_revision",
            "action",
            name="uq_knowledge_vector_job_profile_version",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "document_version_id"],
            ["knowledge_document_versions.tenant_id", "knowledge_document_versions.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "embedding_config_id"],
            ["embedding_configs.tenant_id", "embedding_configs.id"],
            ondelete="RESTRICT",
        ),
        Index(
            "ix_knowledge_vector_job_claim",
            "tenant_id",
            "status",
            "lease_until",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    document_version_id: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding_config_id: Mapped[str | None] = mapped_column(String(64))
    index_revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="queued", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lease_owner: Mapped[str | None] = mapped_column(String(128))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(128))


class KnowledgeVectorReference(Base, TimestampMixin):
    __tablename__ = "knowledge_vector_references"
    __table_args__ = (
        UniqueConstraint("vector_id", name="uq_knowledge_vector_reference_id"),
        ForeignKeyConstraint(
            ["tenant_id", "chunk_id"],
            ["knowledge_chunks.tenant_id", "knowledge_chunks.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "embedding_config_id"],
            ["embedding_configs.tenant_id", "embedding_configs.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "document_version_id"],
            ["knowledge_document_versions.tenant_id", "knowledge_document_versions.id"],
            ondelete="CASCADE",
        ),
        Index(
            "ix_knowledge_vector_reference_version",
            "tenant_id",
            "document_version_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    document_version_id: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding_config_id: Mapped[str | None] = mapped_column(String(64))
    index_revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    chunk_id: Mapped[str] = mapped_column(String(64), nullable=False)
    vector_id: Mapped[str] = mapped_column(String(191), nullable=False)
    collection: Mapped[str] = mapped_column(String(128), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(191), nullable=False)
