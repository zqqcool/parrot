"""Persist remote runtime recovery cursor and lease.

Revision ID: 0012_runtime_recovery
Revises: 0011_agent_skill_merge
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0012_runtime_recovery"
down_revision: str | None = "0011_agent_skill_merge"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "interactions",
        sa.Column("runtime_event_sequence", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "interactions",
        sa.Column("runtime_recovery_lease_owner", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "interactions",
        sa.Column("runtime_recovery_lease_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.alter_column("interactions", "runtime_event_sequence", server_default=None)
    op.create_index(
        "ix_interaction_recovery",
        "interactions",
        ["tenant_id", "status", "runtime_recovery_lease_until"],
    )


def downgrade() -> None:
    op.drop_index("ix_interaction_recovery", table_name="interactions")
    op.drop_column("interactions", "runtime_recovery_lease_until")
    op.drop_column("interactions", "runtime_recovery_lease_owner")
    op.drop_column("interactions", "runtime_event_sequence")
