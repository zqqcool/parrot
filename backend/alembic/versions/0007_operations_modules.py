"""Add tenant run-adjacent memory and schedule modules.

Revision ID: 0007_operations_modules
Revises: 0006_agent_capability_bindings
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007_operations_modules"
down_revision: str | None = "0006_agent_capability_bindings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    _create_memory_records()
    _create_scheduled_tasks()
    _create_schedule_executions()
    for table in ("memory_records", "scheduled_tasks", "schedule_executions"):
        op.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        op.execute(
            sa.text(
                f"CREATE POLICY {table}_tenant_isolation ON {table} "
                "USING (tenant_id = current_setting('app.current_tenant_id', true)) "
                "WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true))"
            )
        )


def _create_memory_records() -> None:
    op.create_table(
        "memory_records",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("agent_id", sa.String(64)),
        sa.Column("scope_type", sa.String(32), nullable=False),
        sa.Column("scope_id", sa.String(128), nullable=False),
        sa.Column("key", sa.String(191), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("memory_type", sa.String(64), nullable=False),
        sa.Column("retention_policy", sa.String(32), nullable=False, server_default="user_managed"),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by_user_id", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "agent_id"],
            ["agent_publications.tenant_id", "agent_publications.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "tenant_id", "scope_type", "scope_id", "key", name="uq_memory_scope_key"
        ),
    )
    op.create_index("ix_memory_tenant_status", "memory_records", ["tenant_id", "status"])
    op.create_index("ix_memory_tenant_agent", "memory_records", ["tenant_id", "agent_id"])


def _create_scheduled_tasks() -> None:
    op.create_table(
        "scheduled_tasks",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("agent_id", sa.String(64), nullable=False),
        sa.Column("creator_user_id", sa.String(64), nullable=False),
        sa.Column("title", sa.String(191), nullable=False),
        sa.Column("input_text", sa.Text(), nullable=False),
        sa.Column("schedule_type", sa.String(32), nullable=False),
        sa.Column("cron_expr", sa.String(128)),
        sa.Column("run_at", sa.DateTime(timezone=True)),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="Asia/Shanghai"),
        sa.Column("status", sa.String(32), nullable=False, server_default="enabled"),
        sa.Column("next_trigger_at", sa.DateTime(timezone=True)),
        sa.Column("last_triggered_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "agent_id"],
            ["agent_publications.tenant_id", "agent_publications.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_schedule_tenant_id"),
    )
    op.create_index(
        "ix_schedule_tenant_status_next",
        "scheduled_tasks",
        ["tenant_id", "status", "next_trigger_at"],
    )
    op.create_index("ix_scheduled_tasks_next_trigger_at", "scheduled_tasks", ["next_trigger_at"])


def _create_schedule_executions() -> None:
    op.create_table(
        "schedule_executions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("schedule_id", sa.String(64), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trigger_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="queued"),
        sa.Column("interaction_id", sa.String(64)),
        sa.Column("error_code", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "schedule_id"],
            ["scheduled_tasks.tenant_id", "scheduled_tasks.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "interaction_id"],
            ["interactions.tenant_id", "interactions.id"],
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("schedule_id", "scheduled_for", name="uq_schedule_execution_trigger"),
    )
    op.create_index(
        "ix_schedule_execution_task_created",
        "schedule_executions",
        ["schedule_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_schedule_execution_task_created", table_name="schedule_executions")
    op.drop_table("schedule_executions")
    op.drop_index("ix_scheduled_tasks_next_trigger_at", table_name="scheduled_tasks")
    op.drop_index("ix_schedule_tenant_status_next", table_name="scheduled_tasks")
    op.drop_table("scheduled_tasks")
    op.drop_index("ix_memory_tenant_agent", table_name="memory_records")
    op.drop_index("ix_memory_tenant_status", table_name="memory_records")
    op.drop_table("memory_records")
