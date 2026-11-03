from __future__ import annotations

from sqlalchemy import (
    JSON,
    Boolean,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base, TimestampMixin


class ImChannel(Base, TimestampMixin):
    __tablename__ = "im_channels"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_im_channel_tenant_name"),
        UniqueConstraint("public_key", name="uq_im_channel_public_key"),
        UniqueConstraint("tenant_id", "id", name="uq_im_channel_tenant_id"),
        Index("ix_im_channel_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    channel_type: Mapped[str] = mapped_column(String(32), nullable=False, default="websocket")
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    public_key: Mapped[str] = mapped_column(String(96), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="enabled")
    allowed_origins: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    config_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)


class ImChannelCredential(Base, TimestampMixin):
    __tablename__ = "im_channel_credentials"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "channel_id"],
            ["im_channels.tenant_id", "im_channels.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("channel_id", "kind", name="uq_im_channel_credential_kind"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    channel_id: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    ciphertext: Mapped[str] = mapped_column(Text, nullable=False)


class ImAgentBinding(Base, TimestampMixin):
    __tablename__ = "im_agent_bindings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "channel_id"],
            ["im_channels.tenant_id", "im_channels.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "agent_id"],
            ["agent_publications.tenant_id", "agent_publications.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("channel_id", name="uq_im_agent_binding_channel"),
        Index("ix_im_agent_binding_tenant_agent", "tenant_id", "agent_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    channel_id: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="enabled")


class ImInboundDelivery(Base, TimestampMixin):
    __tablename__ = "im_inbound_deliveries"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "channel_id"],
            ["im_channels.tenant_id", "im_channels.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "interaction_id"],
            ["interactions.tenant_id", "interactions.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "channel_id",
            "visitor_id",
            "client_message_id",
            name="uq_im_inbound_channel_visitor_message",
        ),
        Index("ix_im_inbound_tenant_channel", "tenant_id", "channel_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    channel_id: Mapped[str] = mapped_column(String(64), nullable=False)
    visitor_id: Mapped[str] = mapped_column(String(64), nullable=False)
    client_message_id: Mapped[str] = mapped_column(String(128), nullable=False)
    interaction_id: Mapped[str | None] = mapped_column(String(64))
    accepted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
