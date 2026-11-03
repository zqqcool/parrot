"""Add a separate raw-message vector indexing outbox.

Revision ID: 0040_message_index_outbox
Revises: 0039_p2p_messages
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0040_message_index_outbox"
down_revision: str | Sequence[str] | None = "0039_p2p_messages"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "conversation_message_index_jobs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("message_id", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False, server_default="index"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="queued"),
        sa.Column("lease_owner", sa.String(length=128)),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(length=128)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "message_id"],
            ["conversation_messages.tenant_id", "conversation_messages.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("tenant_id", "message_id", "action", name="uq_message_index_job_action"),
    )
    op.create_index(
        "ix_message_index_job_claim",
        "conversation_message_index_jobs",
        ["tenant_id", "status", "lease_until", "created_at"],
    )
    op.create_table(
        "conversation_message_vector_references",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("message_id", sa.String(length=64), nullable=False),
        sa.Column("vector_id", sa.String(length=191), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("collection", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "message_id"],
            ["conversation_messages.tenant_id", "conversation_messages.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("vector_id", name="uq_message_vector_reference_id"),
    )
    op.create_index(
        "ix_message_vector_reference_message",
        "conversation_message_vector_references",
        ["tenant_id", "message_id"],
    )
    for table in ("conversation_message_index_jobs", "conversation_message_vector_references"):
        op.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        op.execute(
            sa.text(
                f"CREATE POLICY {table}_tenant_isolation ON {table} "
                "USING (tenant_id = current_setting('app.current_tenant_id', true)) "
                "WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true))"
            )
        )


def downgrade() -> None:
    op.drop_index("ix_message_vector_reference_message", table_name="conversation_message_vector_references")
    op.drop_table("conversation_message_vector_references")
    op.drop_index("ix_message_index_job_claim", table_name="conversation_message_index_jobs")
    op.drop_table("conversation_message_index_jobs")
