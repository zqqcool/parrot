"""Enforce tenant isolation with PostgreSQL row-level security."""

from collections.abc import Sequence

from alembic import op

revision: str = "0002_tenant_row_level_security"
down_revision: str | None = "0001_platform_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_ID = "NULLIF(current_setting('app.current_tenant_id', true), '')"
USER_ID = "NULLIF(current_setting('app.current_user_id', true), '')"

STRICT_TENANT_TABLES = (
    "groups",
    "group_members",
    "group_roles",
    "membership_roles",
    "anonymous_sessions",
    "interactions",
    "interaction_events",
    "idempotency_records",
    "audit_logs",
)


def upgrade() -> None:
    for table in STRICT_TENANT_TABLES:
        _enable(table)
        op.execute(
            f"CREATE POLICY {table}_tenant_access ON {table} "
            f"FOR ALL USING (tenant_id = {TENANT_ID}) "
            f"WITH CHECK (tenant_id = {TENANT_ID})"
        )

    _enable("tenant_memberships")
    op.execute(
        "CREATE POLICY tenant_memberships_select ON tenant_memberships "
        f"FOR SELECT USING (tenant_id = {TENANT_ID} OR user_id = {USER_ID})"
    )
    op.execute(
        "CREATE POLICY tenant_memberships_write ON tenant_memberships "
        f"FOR ALL USING (tenant_id = {TENANT_ID}) "
        f"WITH CHECK (tenant_id = {TENANT_ID})"
    )

    for table in ("roles", "role_permissions"):
        _enable(table)
        op.execute(
            f"CREATE POLICY {table}_global_read ON {table} FOR SELECT USING (tenant_id IS NULL)"
        )
        op.execute(
            f"CREATE POLICY {table}_tenant_access ON {table} "
            f"FOR ALL USING (tenant_id = {TENANT_ID}) "
            f"WITH CHECK (tenant_id = {TENANT_ID})"
        )

    _enable("agent_publications")
    op.execute(
        "CREATE POLICY agent_publications_public_read ON agent_publications "
        "FOR SELECT USING (status = 'active' AND published AND allow_anonymous)"
    )
    op.execute(
        "CREATE POLICY agent_publications_tenant_access ON agent_publications "
        f"FOR ALL USING (tenant_id = {TENANT_ID}) "
        f"WITH CHECK (tenant_id = {TENANT_ID})"
    )


def downgrade() -> None:
    op.execute("DROP POLICY agent_publications_tenant_access ON agent_publications")
    op.execute("DROP POLICY agent_publications_public_read ON agent_publications")
    _disable("agent_publications")

    for table in ("role_permissions", "roles"):
        op.execute(f"DROP POLICY {table}_tenant_access ON {table}")
        op.execute(f"DROP POLICY {table}_global_read ON {table}")
        _disable(table)

    op.execute("DROP POLICY tenant_memberships_write ON tenant_memberships")
    op.execute("DROP POLICY tenant_memberships_select ON tenant_memberships")
    _disable("tenant_memberships")

    for table in reversed(STRICT_TENANT_TABLES):
        op.execute(f"DROP POLICY {table}_tenant_access ON {table}")
        _disable(table)


def _enable(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")


def _disable(table: str) -> None:
    op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
