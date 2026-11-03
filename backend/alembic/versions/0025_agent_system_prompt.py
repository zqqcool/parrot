"""Persist tenant-scoped Agent system prompts.

Revision ID: 0025_agent_system_prompt
Revises: 0024_database_credentials
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0025_agent_system_prompt"
down_revision: str | None = "0024_database_credentials"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_publications",
        sa.Column("system_prompt", sa.Text(), nullable=False, server_default=""),
    )
    op.alter_column("agent_publications", "system_prompt", server_default=None)


def downgrade() -> None:
    op.drop_column("agent_publications", "system_prompt")
