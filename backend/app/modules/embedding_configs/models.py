from __future__ import annotations

from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base, TimestampMixin


class EmbeddingConfig(Base, TimestampMixin):
    __tablename__ = "embedding_configs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_embedding_config_tenant_name"),
        UniqueConstraint("tenant_id", "id", name="uq_embedding_config_tenant_id"),
        Index("ix_embedding_config_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    base_url: Mapped[str] = mapped_column(String(512), nullable=False)
    credential_envelope: Mapped[str | None] = mapped_column(Text)
    embedding_dimension: Mapped[int] = mapped_column(Integer, nullable=False)
    configuration_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
