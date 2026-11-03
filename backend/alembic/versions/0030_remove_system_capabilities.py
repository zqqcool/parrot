"""Remove globally scoped Skill and MCP capabilities.

Revision ID: 0030_remove_system_capabilities
Revises: 0029_user_avatar_storage
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0030_remove_system_capabilities"
down_revision: str | None = "0029_user_avatar_storage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    _reject_unassigned_platform_capabilities()
    op.execute("DROP POLICY audit_logs_platform_capabilities_write ON audit_logs")
    op.execute("DROP POLICY skill_versions_system_write ON skill_versions")
    op.execute("DROP POLICY skill_versions_system_read ON skill_versions")
    _remove_system_scope("skills", "uq_system_skill_name")
    _remove_system_scope("mcp_servers", "uq_system_mcp_server_name")
    op.execute("DELETE FROM role_permissions WHERE permission_key = 'platform.capabilities.manage'")
    op.execute("DELETE FROM permissions WHERE key = 'platform.capabilities.manage'")
    op.alter_column(
        "skill_versions", "tenant_id", existing_type=sa.String(length=64), nullable=False
    )


def downgrade() -> None:
    raise RuntimeError(
        "Downgrading the removal of global Skill and MCP capabilities is unsupported; "
        "restore a pre-migration database backup instead."
    )


def _reject_unassigned_platform_capabilities() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM skills WHERE is_system OR tenant_id IS NULL)
               OR EXISTS (SELECT 1 FROM mcp_servers WHERE is_system OR tenant_id IS NULL)
               OR EXISTS (SELECT 1 FROM skill_versions WHERE tenant_id IS NULL)
            THEN
                RAISE EXCEPTION
                    'Global Skill/MCP records remain. Assign or recreate each capability '
                    'in its owning tenant before applying revision 0030.';
            END IF;
        END $$;
        """
    )


def _remove_system_scope(table: str, index_name: str) -> None:
    op.execute(f"DROP POLICY {table}_system_write ON {table}")
    op.execute(f"DROP POLICY {table}_system_read ON {table}")
    op.drop_index(index_name, table_name=table)
    op.drop_constraint(f"ck_{table}_ownership_scope", table, type_="check")
    op.drop_column(table, "is_system")
    op.alter_column(table, "tenant_id", existing_type=sa.String(length=64), nullable=False)
