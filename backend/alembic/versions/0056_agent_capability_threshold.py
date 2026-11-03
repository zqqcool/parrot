"""Add the Agent capability relevance threshold.

Revision ID: 0056_agent_capability_threshold
Revises: 0055_message_sequence
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0056_agent_capability_threshold"
down_revision: str | None = "0055_message_sequence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_publications",
        sa.Column(
            "capability_relevance_threshold",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0.4"),
        ),
    )
    op.create_check_constraint(
        "ck_agent_capability_relevance_threshold",
        "agent_publications",
        "capability_relevance_threshold >= 0 AND capability_relevance_threshold <= 1",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_agent_capability_relevance_threshold",
        "agent_publications",
        type_="check",
    )
    op.drop_column("agent_publications", "capability_relevance_threshold")
