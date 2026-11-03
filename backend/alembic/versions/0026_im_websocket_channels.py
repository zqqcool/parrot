"""Add tenant-scoped WebSocket IM channels and bindings.

Revision ID: 0026_im_websocket_channels
Revises: 0025_agent_system_prompt
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0026_im_websocket_channels"
down_revision: str | None = "0025_agent_system_prompt"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = (
    "im_channels",
    "im_channel_credentials",
    "im_agent_bindings",
    "im_inbound_deliveries",
)


def upgrade() -> None:
    op.create_table(
        "im_channels",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("channel_type", sa.String(32), nullable=False, server_default="websocket"),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("public_key", sa.String(96), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="enabled"),
        sa.Column(
            "allowed_origins", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")
        ),
        sa.Column("config_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_im_channel_tenant_name"),
        sa.UniqueConstraint("public_key", name="uq_im_channel_public_key"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_im_channel_tenant_id"),
    )
    op.create_index("ix_im_channel_tenant_status", "im_channels", ["tenant_id", "status"])
    op.create_table(
        "im_channel_credentials",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("channel_id", sa.String(64), nullable=False),
        sa.Column("visitor_id", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("ciphertext", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "channel_id"],
            ["im_channels.tenant_id", "im_channels.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("channel_id", "kind", name="uq_im_channel_credential_kind"),
    )
    op.create_table(
        "im_agent_bindings",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("channel_id", sa.String(64), nullable=False),
        sa.Column("agent_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="enabled"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "channel_id"],
            ["im_channels.tenant_id", "im_channels.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "agent_id"],
            ["agent_publications.tenant_id", "agent_publications.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("channel_id", name="uq_im_agent_binding_channel"),
    )
    op.create_index(
        "ix_im_agent_binding_tenant_agent", "im_agent_bindings", ["tenant_id", "agent_id"]
    )
    op.add_column("interactions", sa.Column("im_channel_id", sa.String(64)))
    op.add_column("interactions", sa.Column("im_agent_binding_id", sa.String(64)))
    op.create_index("ix_interaction_im_channel", "interactions", ["im_channel_id"])
    op.create_index("ix_interaction_im_binding", "interactions", ["im_agent_binding_id"])
    op.create_table(
        "im_inbound_deliveries",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("channel_id", sa.String(64), nullable=False),
        sa.Column("visitor_id", sa.String(64), nullable=False),
        sa.Column("client_message_id", sa.String(128), nullable=False),
        sa.Column("interaction_id", sa.String(64)),
        sa.Column("accepted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "channel_id"],
            ["im_channels.tenant_id", "im_channels.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "interaction_id"],
            ["interactions.tenant_id", "interactions.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "channel_id",
            "visitor_id",
            "client_message_id",
            name="uq_im_inbound_channel_visitor_message",
        ),
    )
    op.create_index(
        "ix_im_inbound_tenant_channel", "im_inbound_deliveries", ["tenant_id", "channel_id"]
    )
    op.execute(
        sa.text(
            "CREATE POLICY im_channels_public_read ON im_channels FOR SELECT "
            "USING (channel_type = 'websocket' AND status = 'enabled')"
        )
    )
    for table in _TABLES:
        op.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        op.execute(
            sa.text(
                f"CREATE POLICY {table}_tenant_isolation ON {table} "
                "USING (tenant_id = current_setting('app.current_tenant_id', true)) "
                "WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true))"
            )
        )


def downgrade() -> None:
    op.drop_table("im_inbound_deliveries")
    op.drop_index("ix_interaction_im_binding", table_name="interactions")
    op.drop_index("ix_interaction_im_channel", table_name="interactions")
    op.drop_column("interactions", "im_agent_binding_id")
    op.drop_column("interactions", "im_channel_id")
    op.drop_table("im_agent_bindings")
    op.drop_table("im_channel_credentials")
    op.drop_table("im_channels")
