from __future__ import annotations

from sqlalchemy import (
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base, TimestampMixin


class KnowledgeEvidenceGroup(Base, TimestampMixin):
    __tablename__ = "knowledge_evidence_groups"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_knowledge_evidence_group_tenant_id"),
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
        Index("ix_knowledge_evidence_group_version", "tenant_id", "document_version_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    space_id: Mapped[str] = mapped_column(String(64), nullable=False)
    document_version_id: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    expand_default: Mapped[str] = mapped_column(String(32), default="adjacent_1", nullable=False)
    ordinal_start: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ordinal_end: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class KnowledgeMediaAsset(Base, TimestampMixin):
    __tablename__ = "knowledge_media_assets"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_knowledge_media_asset_tenant_id"),
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
        Index("ix_knowledge_media_asset_version", "tenant_id", "document_version_id"),
        Index("ix_knowledge_media_asset_group", "tenant_id", "group_id", "ordinal_in_group"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    space_id: Mapped[str] = mapped_column(String(64), nullable=False)
    document_version_id: Mapped[str] = mapped_column(String(64), nullable=False)
    group_id: Mapped[str | None] = mapped_column(String(64))
    asset_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    slide_no: Mapped[int | None] = mapped_column(Integer)
    sheet_name: Mapped[str | None] = mapped_column(String(191))
    cell_anchor: Mapped[str | None] = mapped_column(String(64))
    section_path: Mapped[str | None] = mapped_column(String(512))
    ordinal_in_group: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="ready", nullable=False)
