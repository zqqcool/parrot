from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base, TimestampMixin


class Interaction(Base, TimestampMixin):
    __tablename__ = "interactions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_interaction_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "agent_id"],
            ["agent_publications.tenant_id", "agent_publications.id"],
            ondelete="RESTRICT",
        ),
        Index("ix_interaction_tenant_actor", "tenant_id", "actor_type", "actor_id"),
        Index("ix_interaction_recovery", "tenant_id", "status", "runtime_recovery_lease_until"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    agent_id: Mapped[str] = mapped_column(String(64), index=True)
    im_channel_id: Mapped[str | None] = mapped_column(String(64), index=True)
    im_agent_binding_id: Mapped[str | None] = mapped_column(String(64), index=True)
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(64), nullable=False)
    entry_type: Mapped[str] = mapped_column(String(32), nullable=False)
    input_type: Mapped[str] = mapped_column(String(32), nullable=False)
    conversation_id: Mapped[str | None] = mapped_column(String(128), index=True)
    transcript_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    parent_interaction_id: Mapped[str | None] = mapped_column(String(64), index=True)
    root_interaction_id: Mapped[str | None] = mapped_column(String(64), index=True)
    subagent_task_id: Mapped[str | None] = mapped_column(String(64))
    runtime_depth: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="accepted", index=True)
    input_summary: Mapped[str] = mapped_column(Text, default="")
    input_payload: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    runtime_execution_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    runtime_event_sequence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    runtime_recovery_lease_owner: Mapped[str | None] = mapped_column(String(128), nullable=True)
    runtime_recovery_lease_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class InteractionEvent(Base, TimestampMixin):
    __tablename__ = "interaction_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "interaction_id"],
            ["interactions.tenant_id", "interactions.id"],
            ondelete="CASCADE",
        ),
        Index("ix_event_interaction_created", "interaction_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    interaction_id: Mapped[str] = mapped_column(String(64), nullable=False)
    type: Mapped[str] = mapped_column(String(128), nullable=False)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    sequence: Mapped[int] = mapped_column(nullable=False)
    data: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)


class InteractionDiagnosticTrace(Base, TimestampMixin):
    """Management-only runtime diagnostics for one interaction.

    Raw provider-request snapshots are permitted only when the dev/SIT
    ``ai.debug_capture_prompts`` switch was explicitly enabled at execution time.
    """

    __tablename__ = "interaction_diagnostic_traces"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "interaction_id"],
            ["interactions.tenant_id", "interactions.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("interaction_id", "sequence", name="uq_diagnostic_trace_sequence"),
        Index("ix_diagnostic_trace_interaction", "tenant_id", "interaction_id", "sequence"),
        Index("ix_diagnostic_trace_expiry", "tenant_id", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    interaction_id: Mapped[str] = mapped_column(String(64), nullable=False)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    sequence: Mapped[int] = mapped_column(nullable=False)
    data: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class InteractionFinalization(Base, TimestampMixin):
    """Private checkpoint for a final user-visible rendering attempt."""

    __tablename__ = "interaction_finalizations"
    __table_args__ = (
        CheckConstraint(
            "delivery_mode IN ('render', 'candidate')",
            name="ck_interaction_finalization_delivery_mode",
        ),
        CheckConstraint(
            "(delivery_mode = 'render' AND candidate_content IS NULL) OR "
            "(delivery_mode = 'candidate' AND candidate_content IS NOT NULL "
            "AND jsonb_array_length(candidate_deltas) > 0)",
            name="ck_interaction_finalization_delivery_payload",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "interaction_id"],
            ["interactions.tenant_id", "interactions.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("interaction_id", name="uq_interaction_finalization_interaction"),
        Index("ix_interaction_finalization_resume", "tenant_id", "phase"),
        Index("ix_interaction_finalization_expiry", "tenant_id", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    interaction_id: Mapped[str] = mapped_column(String(64), nullable=False)
    phase: Mapped[str] = mapped_column(String(32), nullable=False, default="prepared")
    delivery_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="render")
    output_id: Mapped[str] = mapped_column(String(64), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    terminal_status: Mapped[str] = mapped_column(String(32), nullable=False)
    render_messages: Mapped[list[dict[str, object]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    candidate_content: Mapped[str | None] = mapped_column(Text)
    candidate_deltas: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    completion_data: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ConversationMessage(Base, TimestampMixin):
    """A tenant-private, role-labelled transcript row for one root interaction."""

    __tablename__ = "conversation_messages"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_conversation_message_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "interaction_id",
            "sequence",
            name="uq_conversation_message_interaction_sequence",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "interaction_id"],
            ["interactions.tenant_id", "interactions.id"],
            ondelete="CASCADE",
        ),
        Index(
            "ix_conversation_message_history",
            "tenant_id",
            "agent_id",
            "actor_type",
            "actor_id",
            "conversation_id",
            "created_at",
        ),
        Index(
            "ix_conversation_message_channel_history",
            "tenant_id",
            "im_channel_id",
            "im_agent_binding_id",
            "agent_id",
            "actor_type",
            "actor_id",
            "conversation_id",
            "created_at",
        ),
        UniqueConstraint(
            "tenant_id",
            "im_channel_id",
            "external_message_id",
            name="uq_conversation_message_external",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    interaction_id: Mapped[str] = mapped_column(String(64), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    agent_id: Mapped[str] = mapped_column(String(64), nullable=False)
    im_channel_id: Mapped[str | None] = mapped_column(String(64))
    im_agent_binding_id: Mapped[str | None] = mapped_column(String(64))
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(64), nullable=False)
    conversation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    external_message_id: Mapped[str | None] = mapped_column(String(191))
    provider_message_id: Mapped[str | None] = mapped_column(String(191))
    delivery_status: Mapped[str] = mapped_column(String(32), default="not_required", nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IdempotencyRecord(Base, TimestampMixin):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "actor_type",
            "actor_id",
            "entry_type",
            "idempotency_key",
            name="uq_interaction_idempotency",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "interaction_id"],
            ["interactions.tenant_id", "interactions.id"],
            ondelete="CASCADE",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(64), nullable=False)
    entry_type: Mapped[str] = mapped_column(String(32), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(191), nullable=False)
    interaction_id: Mapped[str] = mapped_column(String(64), nullable=False)
