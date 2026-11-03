"""Add the default marker to the system agent type catalog.

Revision ID: 0013_agent_type_default
Revises: 0012_runtime_recovery
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0013_agent_type_default"
down_revision: str | None = "0012_runtime_recovery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_types",
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.execute(sa.text("UPDATE agent_types SET is_default = true WHERE key = 'knowledge'"))
    op.create_index(
        "uq_agent_types_default",
        "agent_types",
        ["is_default"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )
    op.alter_column("agent_publications", "agent_type_key", server_default=None)


def downgrade() -> None:
    op.alter_column(
        "agent_publications",
        "agent_type_key",
        server_default=sa.text("'knowledge'"),
    )
    op.drop_index("uq_agent_types_default", table_name="agent_types")
    op.drop_column("agent_types", "is_default")
