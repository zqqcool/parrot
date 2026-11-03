"""Keep tenant identity intact when an execution references an interaction.

Revision ID: 0008_schedule_execution_fk
Revises: 0007_operations_modules
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0008_schedule_execution_fk"
down_revision: str | None = "0007_operations_modules"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONSTRAINT = "schedule_executions_tenant_id_interaction_id_fkey"


def upgrade() -> None:
    op.drop_constraint(_CONSTRAINT, "schedule_executions", type_="foreignkey")
    op.create_foreign_key(
        _CONSTRAINT,
        "schedule_executions",
        "interactions",
        ["tenant_id", "interaction_id"],
        ["tenant_id", "id"],
    )


def downgrade() -> None:
    op.drop_constraint(_CONSTRAINT, "schedule_executions", type_="foreignkey")
    op.create_foreign_key(
        _CONSTRAINT,
        "schedule_executions",
        "interactions",
        ["tenant_id", "interaction_id"],
        ["tenant_id", "id"],
        ondelete="SET NULL",
    )
