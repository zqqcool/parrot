from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Computed,
    DateTime,
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


class MemoryRecord(Base, TimestampMixin):
    __tablename__ = "memory_records"
    __table_args__ = (
        UniqueConstraint("tenant_id", "scope_type", "scope_id", "key", name="uq_memory_scope_key"),
        UniqueConstraint("tenant_id", "id", name="uq_memory_record_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "agent_id"],
            ["agent_publications.tenant_id", "agent_publications.id"],
            ondelete="CASCADE",
        ),
        Index("ix_memory_tenant_status", "tenant_id", "status"),
        Index("ix_memory_tenant_agent", "tenant_id", "agent_id"),
        Index(
            "ix_memory_scope_chronology",
            "tenant_id",
            "agent_id",
            "scope_type",
            "scope_id",
            "created_at",
            "id",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    agent_id: Mapped[str | None] = mapped_column(String(64))
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_id: Mapped[str] = mapped_column(String(128), nullable=False)
    key: Mapped[str] = mapped_column(String(191), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    search_vector: Mapped[object] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('simple', coalesce(key, '') || ' ' || coalesce(content, ''))",
            persisted=True,
        ),
        nullable=False,
    )
    memory_type: Mapped[str] = mapped_column(String(64), nullable=False)
    retention_policy: Mapped[str] = mapped_column(String(32), default="user_managed")
    status: Mapped[str] = mapped_column(String(32), default="active")
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_by_user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), default="admin", nullable=False)
    write_intent: Mapped[str] = mapped_column(
        String(32), default="explicit_user_request", nullable=False
    )
    requires_confirmation: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sensitivity_level: Mapped[str] = mapped_column(String(32), default="standard", nullable=False)
    conversation_id: Mapped[str | None] = mapped_column(String(128))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MemoryIndexJob(Base, TimestampMixin):
    __tablename__ = "memory_index_jobs"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "memory_id",
            "memory_version",
            "action",
            name="uq_memory_index_job_version",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "memory_id"],
            ["memory_records.tenant_id", "memory_records.id"],
            ondelete="CASCADE",
        ),
        Index("ix_memory_index_job_claim", "tenant_id", "status", "lease_until", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    memory_id: Mapped[str] = mapped_column(String(64), nullable=False)
    memory_version: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="queued", nullable=False)
    lease_owner: Mapped[str | None] = mapped_column(String(128))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(128))


class MemoryVectorReference(Base, TimestampMixin):
    __tablename__ = "memory_vector_references"
    __table_args__ = (
        UniqueConstraint("vector_id", name="uq_memory_vector_reference_id"),
        ForeignKeyConstraint(
            ["tenant_id", "memory_id"],
            ["memory_records.tenant_id", "memory_records.id"],
            ondelete="CASCADE",
        ),
        Index("ix_memory_vector_reference_memory", "tenant_id", "memory_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    memory_id: Mapped[str] = mapped_column(String(64), nullable=False)
    memory_version: Mapped[int] = mapped_column(Integer, nullable=False)
    vector_id: Mapped[str] = mapped_column(String(191), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    collection: Mapped[str] = mapped_column(String(128), nullable=False)
