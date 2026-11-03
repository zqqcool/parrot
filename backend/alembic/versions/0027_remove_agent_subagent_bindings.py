"""Remove static Agent-to-Agent delegation bindings.

Revision ID: 0027_remove_subagent_bindings
Revises: 0026_im_websocket_channels
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0027_remove_subagent_bindings"
down_revision: str | None = "0026_im_websocket_channels"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("agent_subagent_bindings")


def downgrade() -> None:
    op.create_table(
        "agent_subagent_bindings",
        sa.Column("agent_id", sa.String(64), primary_key=True),
        sa.Column("subagent_id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(
            ["agent_id", "tenant_id"],
            ["agent_publications.id", "agent_publications.tenant_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["subagent_id", "tenant_id"],
            ["agent_publications.id", "agent_publications.tenant_id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_agent_subagent_binding_tenant_agent",
        "agent_subagent_bindings",
        ["tenant_id", "agent_id"],
    )
    op.execute(sa.text("ALTER TABLE agent_subagent_bindings ENABLE ROW LEVEL SECURITY"))
    op.execute(
        sa.text(
            "CREATE POLICY agent_subagent_bindings_tenant_isolation ON agent_subagent_bindings "
            "USING (tenant_id = current_setting('app.current_tenant_id', true)) "
            "WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true))"
        )
    )
