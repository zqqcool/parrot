from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base, TimestampMixin


class Skill(Base, TimestampMixin):
    __tablename__ = "skills"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_skill_tenant_name"),
        UniqueConstraint("tenant_id", "id", name="uq_skill_tenant_id"),
        Index("ix_skill_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="draft")
    version: Mapped[int] = mapped_column(default=1)
    manifest: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    instructions: Mapped[str] = mapped_column(Text, default="")
    package_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    package_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    package_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    package_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    runtime_artifact_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    runtime_artifact_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    runtime_artifact_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    build_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    build_source_checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    current_version_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    draft_version_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class SkillVersion(Base, TimestampMixin):
    __tablename__ = "skill_versions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "skill_id", "version", name="uq_skill_version_sequence"),
        Index("ix_skill_version_tenant_skill_status", "tenant_id", "skill_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    skill_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("skills.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    description: Mapped[str] = mapped_column(Text, default="")
    manifest: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    instructions: Mapped[str] = mapped_column(Text, default="")
    package_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    package_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    package_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    package_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_version_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    published_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    runtime_artifact_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    runtime_artifact_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    runtime_artifact_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    build_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    build_source_checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)


class SkillBuildJob(Base, TimestampMixin):
    __tablename__ = "skill_build_jobs"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "skill_version_id",
            "source_checksum",
            name="uq_skill_build_source",
        ),
        Index("ix_skill_build_job_claim", "tenant_id", "status", "lease_until", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    skill_version_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("skill_versions.id", ondelete="CASCADE"), nullable=False
    )
    source_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    lease_owner: Mapped[str | None] = mapped_column(String(128))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(128))
