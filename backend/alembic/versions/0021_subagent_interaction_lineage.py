"""Add durable parent-child interaction lineage for TaskBoard orchestration.

Revision ID: 0021_subagent_lineage
Revises: 0020_agent_subagent_bindings
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0021_subagent_lineage"
down_revision: str | None = "0020_agent_subagent_bindings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("interactions", sa.Column("parent_interaction_id", sa.String(64)))
    op.add_column("interactions", sa.Column("root_interaction_id", sa.String(64)))
    op.add_column("interactions", sa.Column("subagent_task_id", sa.String(64)))
    op.add_column(
        "interactions",
        sa.Column("runtime_depth", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index(
        "ix_interactions_parent_interaction_id", "interactions", ["parent_interaction_id"]
    )
    op.create_index("ix_interactions_root_interaction_id", "interactions", ["root_interaction_id"])
    op.create_foreign_key(
        "fk_interactions_parent_interaction",
        "interactions",
        "interactions",
        ["parent_interaction_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_interactions_root_interaction",
        "interactions",
        "interactions",
        ["root_interaction_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_interactions_root_interaction", "interactions", type_="foreignkey")
    op.drop_constraint("fk_interactions_parent_interaction", "interactions", type_="foreignkey")
    op.drop_index("ix_interactions_root_interaction_id", table_name="interactions")
    op.drop_index("ix_interactions_parent_interaction_id", table_name="interactions")
    op.drop_column("interactions", "runtime_depth")
    op.drop_column("interactions", "subagent_task_id")
    op.drop_column("interactions", "root_interaction_id")
    op.drop_column("interactions", "parent_interaction_id")
