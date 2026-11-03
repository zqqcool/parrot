"""Persist managed agent-avatar object metadata.

Revision ID: 0009_agent_avatar_storage
Revises: 0008_schedule_execution_fk
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009_agent_avatar_storage"
down_revision: str | None = "0008_schedule_execution_fk"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_publications",
        sa.Column("avatar_key", sa.String(length=256), nullable=True),
    )
    op.add_column(
        "agent_publications", sa.Column("avatar_content_type", sa.String(length=64), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("agent_publications", "avatar_content_type")
    op.drop_column("agent_publications", "avatar_key")
