"""Add tenant-private conversation transcript messages.

Revision ID: 0022_conversation_messages
Revises: 0021_subagent_lineage
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0022_conversation_messages"
down_revision: str | None = "0021_subagent_lineage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conversation_messages",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("interaction_id", sa.String(64), nullable=False),
        sa.Column("agent_id", sa.String(64), nullable=False),
        sa.Column("actor_type", sa.String(32), nullable=False),
        sa.Column("actor_id", sa.String(64), nullable=False),
        sa.Column("conversation_id", sa.String(128), nullable=False),
        sa.Column("thread_id", sa.String(128)),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "interaction_id"],
            ["interactions.tenant_id", "interactions.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "tenant_id", "interaction_id", "role", name="uq_conversation_message_interaction_role"
        ),
    )
    op.create_index(
        "ix_conversation_message_history",
        "conversation_messages",
        [
            "tenant_id",
            "agent_id",
            "actor_type",
            "actor_id",
            "conversation_id",
            "thread_id",
            "created_at",
        ],
    )
    op.execute(sa.text("ALTER TABLE conversation_messages ENABLE ROW LEVEL SECURITY"))
    op.execute(
        sa.text(
            "CREATE POLICY conversation_messages_tenant_isolation ON conversation_messages "
            "USING (tenant_id = current_setting('app.current_tenant_id', true)) "
            "WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true))"
        )
    )


def downgrade() -> None:
    op.drop_index("ix_conversation_message_history", table_name="conversation_messages")
    op.drop_table("conversation_messages")
