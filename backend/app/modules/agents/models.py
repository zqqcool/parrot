from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.agent_runtime import DEFAULT_CAPABILITY_RELEVANCE_THRESHOLD
from app.infrastructure.db.base import Base, TimestampMixin


class AgentType(Base):
    """System-owned catalog of supported agent interaction profiles."""

    __tablename__ = "agent_types"

    key: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    is_default: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=text("false"),
        nullable=False,
    )


class AgentPublication(Base, TimestampMixin):
    __tablename__ = "agent_publications"
    __table_args__ = (
        UniqueConstraint("tenant_id", "runtime_agent_id", name="uq_agent_runtime_tenant"),
        UniqueConstraint("tenant_id", "id", name="uq_agent_tenant_id"),
        UniqueConstraint("slug", name="uq_agent_public_slug"),
        Index("ix_agent_tenant_status", "tenant_id", "status"),
        CheckConstraint(
            "capability_relevance_threshold >= 0 AND capability_relevance_threshold <= 1",
            name="ck_agent_capability_relevance_threshold",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    runtime_agent_id: Mapped[str] = mapped_column(String(128), nullable=False)
    slug: Mapped[str] = mapped_column(String(150), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str] = mapped_column(String(1000), default="")
    system_prompt: Mapped[str] = mapped_column(Text, default="", nullable=False)
    capability_relevance_threshold: Mapped[float] = mapped_column(
        Float,
        default=DEFAULT_CAPABILITY_RELEVANCE_THRESHOLD,
        server_default=text(str(DEFAULT_CAPABILITY_RELEVANCE_THRESHOLD)),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), default="active")
    agent_type_key: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("agent_types.key", ondelete="RESTRICT"),
        nullable=False,
    )
    published: Mapped[bool] = mapped_column(Boolean, default=False)
    allow_anonymous: Mapped[bool] = mapped_column(Boolean, default=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    avatar_key: Mapped[str | None] = mapped_column(String(256))
    avatar_content_type: Mapped[str | None] = mapped_column(String(64))


class AgentLlmConfigBinding(Base):
    __tablename__ = "agent_llm_config_bindings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["agent_id", "tenant_id"],
            ["agent_publications.id", "agent_publications.tenant_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["llm_config_id", "tenant_id"],
            ["llm_configs.id", "llm_configs.tenant_id"],
            ondelete="CASCADE",
        ),
        Index("ix_agent_llm_binding_tenant_agent", "tenant_id", "agent_id"),
        UniqueConstraint("tenant_id", "agent_id", name="uq_agent_llm_binding_tenant_agent"),
        Index(
            "uq_agent_default_llm",
            "tenant_id",
            "agent_id",
            unique=True,
            postgresql_where=text("is_default"),
        ),
    )

    agent_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    llm_config_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class AgentSkillBinding(Base):
    __tablename__ = "agent_skill_bindings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["agent_id", "tenant_id"],
            ["agent_publications.id", "agent_publications.tenant_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["skill_id", "tenant_id"],
            ["skills.id", "skills.tenant_id"],
            ondelete="RESTRICT",
        ),
        Index("ix_agent_skill_binding_tenant_agent", "tenant_id", "agent_id"),
    )

    agent_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    skill_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)


class AgentMcpServerBinding(Base):
    __tablename__ = "agent_mcp_server_bindings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["agent_id", "tenant_id"],
            ["agent_publications.id", "agent_publications.tenant_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["mcp_server_id", "tenant_id"],
            ["mcp_servers.id", "mcp_servers.tenant_id"],
            ondelete="CASCADE",
        ),
        Index("ix_agent_mcp_binding_tenant_agent", "tenant_id", "agent_id"),
    )

    agent_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    mcp_server_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
