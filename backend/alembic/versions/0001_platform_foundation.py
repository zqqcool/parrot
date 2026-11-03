"""Create the platform identity, tenancy, agent, and interaction schema."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001_platform_foundation"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> tuple[sa.Column[sa.DateTime], sa.Column[sa.DateTime]]:
    return (
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def upgrade() -> None:
    op.create_table(
        "permissions",
        sa.Column("key", sa.String(128), primary_key=True),
        sa.Column("description", sa.String(255), nullable=False),
    )
    op.create_table(
        "tenants",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        *_timestamps(),
    )
    op.create_index("ix_tenants_slug", "tenants", ["slug"], unique=True)
    op.create_index("ix_tenants_status", "tenants", ["status"])

    op.create_table(
        "users",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("username", sa.String(150), nullable=False),
        sa.Column("normalized_username", sa.String(150), nullable=False),
        sa.Column("email", sa.String(254), unique=True),
        sa.Column("display_name", sa.String(150), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        *_timestamps(),
    )
    op.create_index("ix_users_normalized_username", "users", ["normalized_username"], unique=True)
    op.create_index("ix_users_status", "users", ["status"])

    op.create_table(
        "credentials",
        sa.Column(
            "user_id",
            sa.String(64),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("password_hash", sa.Text(), nullable=False),
        *_timestamps(),
    )
    op.create_table(
        "external_identities",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "user_id", sa.String(64), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("subject", sa.String(191), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("provider", "subject", name="uq_external_identity"),
    )
    op.create_index("ix_external_identities_user_id", "external_identities", ["user_id"])

    op.create_table(
        "roles",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), sa.ForeignKey("tenants.id", ondelete="CASCADE")),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("description", sa.String(512), nullable=False, server_default=""),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        *_timestamps(),
        sa.UniqueConstraint("tenant_id", "key", name="uq_roles_tenant_key"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_roles_tenant_id"),
    )
    op.create_index("ix_roles_tenant_id", "roles", ["tenant_id"])
    op.create_index("ix_roles_tenant_status", "roles", ["tenant_id", "status"])
    op.create_index(
        "uq_platform_role_key",
        "roles",
        ["key"],
        unique=True,
        postgresql_where=sa.text("tenant_id IS NULL"),
    )
    op.create_table(
        "role_permissions",
        sa.Column("tenant_id", sa.String(64), sa.ForeignKey("tenants.id", ondelete="CASCADE")),
        sa.Column(
            "role_id",
            sa.String(64),
            sa.ForeignKey("roles.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "permission_key",
            sa.String(128),
            sa.ForeignKey("permissions.key", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "role_id"], ["roles.tenant_id", "roles.id"], ondelete="CASCADE"
        ),
    )
    op.create_index("ix_role_permissions_tenant_id", "role_permissions", ["tenant_id"])
    op.create_table(
        "user_roles",
        sa.Column(
            "user_id",
            sa.String(64),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "role_id",
            sa.String(64),
            sa.ForeignKey("roles.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    op.create_table(
        "tenant_memberships",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(64),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.String(64),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        *_timestamps(),
        sa.UniqueConstraint("tenant_id", "user_id", name="uq_tenant_membership"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_membership_tenant_id"),
    )
    op.create_index("ix_membership_tenant_status", "tenant_memberships", ["tenant_id", "status"])
    op.create_index("ix_tenant_memberships_user_id", "tenant_memberships", ["user_id"])

    op.create_table(
        "sessions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "user_id", sa.String(64), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "current_tenant_id",
            sa.String(64),
            sa.ForeignKey("tenants.id", ondelete="SET NULL"),
        ),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idle_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("user_agent", sa.String(512)),
        *_timestamps(),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_index("ix_sessions_current_tenant_id", "sessions", ["current_tenant_id"])
    op.create_index("ix_sessions_token_hash", "sessions", ["token_hash"], unique=True)
    op.create_index("ix_sessions_revoked_at", "sessions", ["revoked_at"])

    op.create_table(
        "groups",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(64),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("description", sa.String(512), nullable=False, server_default=""),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        *_timestamps(),
        sa.UniqueConstraint("tenant_id", "name", name="uq_group_tenant_name"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_group_tenant_id"),
    )
    op.create_index("ix_groups_tenant_id", "groups", ["tenant_id"])
    op.create_table(
        "group_members",
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("group_id", sa.String(64), primary_key=True),
        sa.Column("membership_id", sa.String(64), primary_key=True),
        sa.ForeignKeyConstraint(
            ["tenant_id", "group_id"], ["groups.tenant_id", "groups.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "membership_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_group_members_tenant_id", "group_members", ["tenant_id"])
    op.create_table(
        "group_roles",
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("group_id", sa.String(64), primary_key=True),
        sa.Column("role_id", sa.String(64), primary_key=True),
        sa.ForeignKeyConstraint(
            ["tenant_id", "group_id"], ["groups.tenant_id", "groups.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "role_id"], ["roles.tenant_id", "roles.id"], ondelete="CASCADE"
        ),
    )
    op.create_index("ix_group_roles_tenant_id", "group_roles", ["tenant_id"])
    op.create_table(
        "membership_roles",
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("membership_id", sa.String(64), primary_key=True),
        sa.Column("role_id", sa.String(64), primary_key=True),
        sa.ForeignKeyConstraint(
            ["tenant_id", "membership_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "role_id"], ["roles.tenant_id", "roles.id"], ondelete="CASCADE"
        ),
    )
    op.create_index("ix_membership_roles_tenant_id", "membership_roles", ["tenant_id"])

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), sa.ForeignKey("tenants.id", ondelete="RESTRICT")),
        sa.Column("actor_type", sa.String(32), nullable=False),
        sa.Column("actor_id", sa.String(64), nullable=False),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.String(64)),
        sa.Column("request_id", sa.String(128), nullable=False),
        sa.Column("succeeded", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        *_timestamps(),
    )
    op.create_index("ix_audit_logs_tenant_id", "audit_logs", ["tenant_id"])
    op.create_index("ix_audit_tenant_created", "audit_logs", ["tenant_id", "created_at"])

    _create_agent_interaction_tables()


def _create_agent_interaction_tables() -> None:
    op.create_table(
        "agent_publications",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(64),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("runtime_agent_id", sa.String(128), nullable=False),
        sa.Column("slug", sa.String(150), nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("description", sa.String(1000), nullable=False, server_default=""),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("published", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("allow_anonymous", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        *_timestamps(),
        sa.UniqueConstraint("tenant_id", "runtime_agent_id", name="uq_agent_runtime_tenant"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_agent_tenant_id"),
        sa.UniqueConstraint("slug", name="uq_agent_public_slug"),
    )
    op.create_index("ix_agent_tenant_status", "agent_publications", ["tenant_id", "status"])
    op.create_table(
        "anonymous_sessions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(64),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        *_timestamps(),
    )
    op.create_index("ix_anonymous_sessions_tenant_id", "anonymous_sessions", ["tenant_id"])
    op.create_index(
        "ix_anonymous_sessions_token_hash", "anonymous_sessions", ["token_hash"], unique=True
    )
    op.create_table(
        "interactions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(64),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("agent_id", sa.String(64), nullable=False),
        sa.Column("actor_type", sa.String(32), nullable=False),
        sa.Column("actor_id", sa.String(64), nullable=False),
        sa.Column("entry_type", sa.String(32), nullable=False),
        sa.Column("input_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="accepted"),
        sa.Column("input_summary", sa.Text(), nullable=False, server_default=""),
        *_timestamps(),
        sa.UniqueConstraint("tenant_id", "id", name="uq_interaction_tenant_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "agent_id"],
            ["agent_publications.tenant_id", "agent_publications.id"],
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_interactions_tenant_id", "interactions", ["tenant_id"])
    op.create_index("ix_interactions_agent_id", "interactions", ["agent_id"])
    op.create_index("ix_interactions_status", "interactions", ["status"])
    op.create_index(
        "ix_interaction_tenant_actor", "interactions", ["tenant_id", "actor_type", "actor_id"]
    )
    op.create_table(
        "interaction_events",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("interaction_id", sa.String(64), nullable=False),
        sa.Column("type", sa.String(128), nullable=False),
        sa.Column("request_id", sa.String(128), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["tenant_id", "interaction_id"],
            ["interactions.tenant_id", "interactions.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_interaction_events_tenant_id", "interaction_events", ["tenant_id"])
    op.create_index(
        "ix_event_interaction_created", "interaction_events", ["interaction_id", "created_at"]
    )
    op.create_table(
        "idempotency_records",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("actor_type", sa.String(32), nullable=False),
        sa.Column("actor_id", sa.String(64), nullable=False),
        sa.Column("entry_type", sa.String(32), nullable=False),
        sa.Column("idempotency_key", sa.String(191), nullable=False),
        sa.Column("interaction_id", sa.String(64), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint(
            "tenant_id",
            "actor_type",
            "actor_id",
            "entry_type",
            "idempotency_key",
            name="uq_interaction_idempotency",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "interaction_id"],
            ["interactions.tenant_id", "interactions.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_idempotency_records_tenant_id", "idempotency_records", ["tenant_id"])


def downgrade() -> None:
    for table in (
        "idempotency_records",
        "interaction_events",
        "interactions",
        "anonymous_sessions",
        "agent_publications",
        "audit_logs",
        "membership_roles",
        "group_roles",
        "group_members",
        "groups",
        "sessions",
        "tenant_memberships",
        "user_roles",
        "role_permissions",
        "roles",
        "external_identities",
        "credentials",
        "users",
        "tenants",
        "permissions",
    ):
        op.drop_table(table)
