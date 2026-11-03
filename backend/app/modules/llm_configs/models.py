from __future__ import annotations

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base, TimestampMixin


class LlmConfig(Base, TimestampMixin):
    __tablename__ = "llm_configs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_llm_config_tenant_name"),
        UniqueConstraint("tenant_id", "id", name="uq_llm_config_tenant_id"),
        Index("ix_llm_config_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(512))
    credential_envelope: Mapped[str | None] = mapped_column(Text)
    temperature: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.2, server_default="0.2"
    )
    max_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, default=4096, server_default="4096"
    )
    # Administrator-declared runtime intent. The baseline OpenAI-compatible
    # adapter does not translate this into provider-specific request fields.
    thinking_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # Administrator-declared prompt-cache capability for the configured endpoint.
    # When true, the adapter may send prompt_cache_key / stream usage options.
    prompt_cache_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    status: Mapped[str] = mapped_column(String(32), default="active")

    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
