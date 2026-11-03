from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base, TimestampMixin


class ScheduledTask(Base, TimestampMixin):
    __tablename__ = "scheduled_tasks"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_schedule_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "agent_id"],
            ["agent_publications.tenant_id", "agent_publications.id"],
            ondelete="CASCADE",
        ),
        Index("ix_schedule_tenant_status_next", "tenant_id", "status", "next_trigger_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    agent_id: Mapped[str] = mapped_column(String(64), nullable=False)
    creator_user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(191), nullable=False)
    input_text: Mapped[str] = mapped_column(Text, nullable=False)
    schedule_type: Mapped[str] = mapped_column(String(32), nullable=False)
    cron_expr: Mapped[str | None] = mapped_column(String(128))
    run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="enabled")
    next_trigger_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ScheduleExecution(Base, TimestampMixin):
    __tablename__ = "schedule_executions"
    __table_args__ = (
        UniqueConstraint("schedule_id", "scheduled_for", name="uq_schedule_execution_trigger"),
        ForeignKeyConstraint(
            ["tenant_id", "schedule_id"],
            ["scheduled_tasks.tenant_id", "scheduled_tasks.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "interaction_id"],
            ["interactions.tenant_id", "interactions.id"],
        ),
        Index("ix_schedule_execution_task_created", "schedule_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    schedule_id: Mapped[str] = mapped_column(String(64), nullable=False)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="queued")
    interaction_id: Mapped[str | None] = mapped_column(String(64))
    error_code: Mapped[str | None] = mapped_column(String(128))
