"""Add tenant-owned LLM, skill, and MCP configuration modules.

Revision ID: 0005_agent_capability_catalog
Revises: 0004_runtime_execution_mapping
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005_agent_capability_catalog"
down_revision: str | None = "0004_runtime_execution_mapping"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "llm_configs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(64),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("base_url", sa.String(512)),
        sa.Column("credential_ref", sa.String(256)),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "name", name="uq_llm_config_tenant_name"),
    )
    op.create_index("ix_llm_config_tenant_status", "llm_configs", ["tenant_id", "status"])
    op.create_table(
        "skills",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(64),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "manifest", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("instructions", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "name", name="uq_skill_tenant_name"),
    )
    op.create_index("ix_skill_tenant_status", "skills", ["tenant_id", "status"])
    op.create_table(
        "mcp_servers",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(64),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("transport", sa.String(32), nullable=False),
        sa.Column("endpoint", sa.String(512), nullable=False),
        sa.Column(
            "secret_refs", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "name", name="uq_mcp_server_tenant_name"),
    )
    op.create_index("ix_mcp_server_tenant_status", "mcp_servers", ["tenant_id", "status"])
    for table in ("llm_configs", "skills", "mcp_servers"):
        op.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        op.execute(
            sa.text(
                f"CREATE POLICY {table}_tenant_isolation ON {table} "
                "USING (tenant_id = current_setting('app.current_tenant_id', true)) "
                "WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true))"
            )
        )


def downgrade() -> None:
    for table, index in (
        ("mcp_servers", "ix_mcp_server_tenant_status"),
        ("skills", "ix_skill_tenant_status"),
        ("llm_configs", "ix_llm_config_tenant_status"),
    ):
        op.drop_index(index, table_name=table)
        op.drop_table(table)
