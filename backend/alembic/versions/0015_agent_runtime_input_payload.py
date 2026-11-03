"""Persist replay-safe inputs for in-process Agent runtime recovery.

Revision ID: 0015_agent_runtime_input_payload
Revises: 0014_skill_version_workbench
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0015_agent_runtime_input_payload"
down_revision: str | None = "0014_skill_version_workbench"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "interactions",
        sa.Column("input_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
    )
    op.alter_column("interactions", "input_payload", server_default=None)


def downgrade() -> None:
    op.drop_column("interactions", "input_payload")
