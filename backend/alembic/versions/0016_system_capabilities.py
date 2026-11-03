"""Add platform-owned Skills and MCP server configurations.

Revision ID: 0016_system_capabilities
Revises: 0015_agent_runtime_input_payload
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0016_system_capabilities"
down_revision: str | None = "0015_agent_runtime_input_payload"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SYSTEM_SCOPE = "current_setting('app.platform_capabilities_manage', true) = 'true'"
_TENANT_SCOPE = "tenant_id = current_setting('app.current_tenant_id', true)"


def upgrade() -> None:
    _add_system_scope("skills")
    _add_system_scope("mcp_servers")
    op.alter_column(
        "skill_versions", "tenant_id", existing_type=sa.String(length=64), nullable=True
    )
    op.execute("ALTER TABLE skill_versions ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY skill_versions_tenant_isolation ON skill_versions "
        f"FOR ALL USING ({_TENANT_SCOPE}) WITH CHECK ({_TENANT_SCOPE})"
    )
    op.execute(
        "CREATE POLICY skill_versions_system_read ON skill_versions "
        "FOR SELECT USING (tenant_id IS NULL)"
    )
    op.execute(
        "CREATE POLICY skill_versions_system_write ON skill_versions FOR ALL "
        f"USING (tenant_id IS NULL AND {_SYSTEM_SCOPE}) "
        f"WITH CHECK (tenant_id IS NULL AND {_SYSTEM_SCOPE})"
    )
    op.execute(
        "CREATE POLICY audit_logs_platform_capabilities_write ON audit_logs FOR INSERT "
        f"WITH CHECK (tenant_id IS NULL AND {_SYSTEM_SCOPE})"
    )


def downgrade() -> None:
    op.execute("DROP POLICY audit_logs_platform_capabilities_write ON audit_logs")
    op.execute("DROP POLICY skill_versions_system_write ON skill_versions")
    op.execute("DROP POLICY skill_versions_system_read ON skill_versions")
    op.execute("DROP POLICY skill_versions_tenant_isolation ON skill_versions")
    op.execute("ALTER TABLE skill_versions DISABLE ROW LEVEL SECURITY")
    op.alter_column(
        "skill_versions", "tenant_id", existing_type=sa.String(length=64), nullable=False
    )
    _remove_system_scope("mcp_servers")
    _remove_system_scope("skills")


def _add_system_scope(table: str) -> None:
    op.alter_column(table, "tenant_id", existing_type=sa.String(length=64), nullable=True)
    op.add_column(
        table, sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.add_column(table, sa.Column("created_by", sa.String(length=64), nullable=True))
    op.create_check_constraint(
        f"ck_{table}_ownership_scope",
        table,
        "(is_system AND tenant_id IS NULL) OR ((NOT is_system) AND tenant_id IS NOT NULL)",
    )
    name_index = "uq_system_skill_name" if table == "skills" else "uq_system_mcp_server_name"
    op.create_index(
        name_index,
        table,
        ["name"],
        unique=True,
        postgresql_where=sa.text("is_system AND tenant_id IS NULL"),
    )
    op.execute(
        f"CREATE POLICY {table}_system_read ON {table} "
        "FOR SELECT USING (is_system AND tenant_id IS NULL)"
    )
    op.execute(
        f"CREATE POLICY {table}_system_write ON {table} FOR ALL "
        f"USING (is_system AND tenant_id IS NULL AND {_SYSTEM_SCOPE}) "
        f"WITH CHECK (is_system AND tenant_id IS NULL AND {_SYSTEM_SCOPE})"
    )


def _remove_system_scope(table: str) -> None:
    name_index = "uq_system_skill_name" if table == "skills" else "uq_system_mcp_server_name"
    op.execute(f"DROP POLICY {table}_system_write ON {table}")
    op.execute(f"DROP POLICY {table}_system_read ON {table}")
    op.drop_index(name_index, table_name=table)
    op.drop_constraint(f"ck_{table}_ownership_scope", table, type_="check")
    op.drop_column(table, "created_by")
    op.drop_column(table, "is_system")
    op.alter_column(table, "tenant_id", existing_type=sa.String(length=64), nullable=False)
