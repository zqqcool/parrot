"""Map Parrot interactions to external runtime executions."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_runtime_execution_mapping"
down_revision: str | None = "0003_interaction_event_sequence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "interactions",
        sa.Column("runtime_execution_id", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_interactions_runtime_execution_id",
        "interactions",
        ["runtime_execution_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_interactions_runtime_execution_id", table_name="interactions")
    op.drop_column("interactions", "runtime_execution_id")
