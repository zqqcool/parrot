"""Add Agent-scoped tenant MCP bindings and transport arguments.

Revision ID: 0017_agent_mcp_bindings
Revises: 0016_system_capabilities
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0017_agent_mcp_bindings"
down_revision: str | None = "0016_system_capabilities"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint("uq_mcp_server_tenant_id", "mcp_servers", ["tenant_id", "id"])
    op.add_column(
        "mcp_servers",
        sa.Column(
            "arguments",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.create_table(
        "agent_mcp_server_bindings",
        sa.Column("agent_id", sa.String(length=64), nullable=False),
        sa.Column("mcp_server_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["agent_id", "tenant_id"],
            ["agent_publications.id", "agent_publications.tenant_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["mcp_server_id", "tenant_id"],
            ["mcp_servers.id", "mcp_servers.tenant_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("agent_id", "mcp_server_id"),
    )
    op.create_index(
        "ix_agent_mcp_binding_tenant_agent",
        "agent_mcp_server_bindings",
        ["tenant_id", "agent_id"],
    )
    op.execute("ALTER TABLE agent_mcp_server_bindings ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY agent_mcp_server_bindings_tenant_isolation "
        "ON agent_mcp_server_bindings FOR ALL "
        "USING (tenant_id = current_setting('app.current_tenant_id', true)) "
        "WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true))"
    )


def downgrade() -> None:
    op.execute(
        "DROP POLICY agent_mcp_server_bindings_tenant_isolation ON agent_mcp_server_bindings"
    )
    op.drop_index("ix_agent_mcp_binding_tenant_agent", table_name="agent_mcp_server_bindings")
    op.drop_table("agent_mcp_server_bindings")
    op.drop_column("mcp_servers", "arguments")
    op.drop_constraint("uq_mcp_server_tenant_id", "mcp_servers", type_="unique")
