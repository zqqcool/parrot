"""Add runtime memory ownership, confirmation, and expiry metadata.

Revision ID: 0018_runtime_memory_metadata
Revises: 0017_agent_mcp_bindings
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0018_runtime_memory_metadata"
down_revision: str | None = "0017_agent_mcp_bindings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "memory_records",
        sa.Column("source_type", sa.String(32), server_default="admin", nullable=False),
    )
    op.add_column(
        "memory_records",
        sa.Column(
            "write_intent",
            sa.String(32),
            server_default="explicit_user_request",
            nullable=False,
        ),
    )
    op.add_column(
        "memory_records",
        sa.Column("requires_confirmation", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "memory_records",
        sa.Column("sensitivity_level", sa.String(32), server_default="standard", nullable=False),
    )
    op.add_column("memory_records", sa.Column("conversation_id", sa.String(128)))
    op.add_column("memory_records", sa.Column("thread_id", sa.String(128)))
    op.add_column("memory_records", sa.Column("expires_at", sa.DateTime(timezone=True)))
    op.create_index(
        "ix_memory_runtime_context",
        "memory_records",
        ["tenant_id", "status", "agent_id", "scope_type", "expires_at"],
    )
    op.add_column("interactions", sa.Column("conversation_id", sa.String(128)))
    op.add_column("interactions", sa.Column("thread_id", sa.String(128)))
    op.create_index("ix_interactions_conversation_id", "interactions", ["conversation_id"])
    op.create_index("ix_interactions_thread_id", "interactions", ["thread_id"])


def downgrade() -> None:
    op.drop_index("ix_interactions_thread_id", table_name="interactions")
    op.drop_index("ix_interactions_conversation_id", table_name="interactions")
    op.drop_column("interactions", "thread_id")
    op.drop_column("interactions", "conversation_id")
    op.drop_index("ix_memory_runtime_context", table_name="memory_records")
    op.drop_column("memory_records", "expires_at")
    op.drop_column("memory_records", "thread_id")
    op.drop_column("memory_records", "conversation_id")
    op.drop_column("memory_records", "sensitivity_level")
    op.drop_column("memory_records", "requires_confirmation")
    op.drop_column("memory_records", "write_intent")
    op.drop_column("memory_records", "source_type")
