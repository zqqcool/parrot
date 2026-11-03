"""Add durable per-interaction event ordering."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_interaction_event_sequence"
down_revision: str | None = "0002_tenant_row_level_security"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "interaction_events",
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"),
    )
    op.execute(
        """
        WITH ordered AS (
            SELECT id, row_number() OVER (
                PARTITION BY interaction_id ORDER BY created_at, id
            ) AS sequence
            FROM interaction_events
        )
        UPDATE interaction_events AS target
        SET sequence = ordered.sequence
        FROM ordered
        WHERE target.id = ordered.id
        """
    )
    op.alter_column("interaction_events", "sequence", server_default=None)
    op.create_index(
        "uq_event_interaction_sequence",
        "interaction_events",
        ["interaction_id", "sequence"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_event_interaction_sequence", table_name="interaction_events")
    op.drop_column("interaction_events", "sequence")
