"""Persist replayable terminal response candidates.

Revision ID: 0051_finalization_candidates
Revises: 0050_finalization_checkpoint
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0051_finalization_candidates"
down_revision: str | None = "0050_finalization_checkpoint"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "interaction_finalizations",
        sa.Column(
            "delivery_mode",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'render'"),
        ),
    )
    op.add_column(
        "interaction_finalizations",
        sa.Column("candidate_content", sa.Text(), nullable=True),
    )
    op.add_column(
        "interaction_finalizations",
        sa.Column(
            "candidate_deltas",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.create_check_constraint(
        "ck_interaction_finalization_delivery_mode",
        "interaction_finalizations",
        "delivery_mode IN ('render', 'candidate')",
    )
    op.create_check_constraint(
        "ck_interaction_finalization_delivery_payload",
        "interaction_finalizations",
        "(delivery_mode = 'render' AND candidate_content IS NULL) OR "
        "(delivery_mode = 'candidate' AND candidate_content IS NOT NULL "
        "AND jsonb_array_length(candidate_deltas) > 0)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_interaction_finalization_delivery_payload",
        "interaction_finalizations",
        type_="check",
    )
    op.drop_constraint(
        "ck_interaction_finalization_delivery_mode",
        "interaction_finalizations",
        type_="check",
    )
    op.drop_column("interaction_finalizations", "candidate_deltas")
    op.drop_column("interaction_finalizations", "candidate_content")
    op.drop_column("interaction_finalizations", "delivery_mode")
