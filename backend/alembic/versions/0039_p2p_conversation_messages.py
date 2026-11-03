"""Add P2P transcript ownership and delivery metadata.

Revision ID: 0039_p2p_messages
Revises: 0038_embedding_snapshots
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0039_p2p_messages"
down_revision: str | None = "0038_embedding_snapshots"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "interactions",
        sa.Column("conversation_kind", sa.String(length=16), nullable=False, server_default="p2p"),
    )
    op.add_column("interactions", sa.Column("transcript_expires_at", sa.DateTime(timezone=True)))
    op.add_column("conversation_messages", sa.Column("im_channel_id", sa.String(length=64)))
    op.add_column("conversation_messages", sa.Column("im_agent_binding_id", sa.String(length=64)))
    op.add_column(
        "conversation_messages",
        sa.Column("conversation_kind", sa.String(length=16), nullable=False, server_default="p2p"),
    )
    op.add_column(
        "conversation_messages",
        sa.Column("direction", sa.String(length=16), nullable=False, server_default="inbound"),
    )
    op.add_column("conversation_messages", sa.Column("external_message_id", sa.String(length=191)))
    op.add_column("conversation_messages", sa.Column("provider_message_id", sa.String(length=191)))
    op.add_column(
        "conversation_messages",
        sa.Column(
            "delivery_status", sa.String(length=32), nullable=False, server_default="not_required"
        ),
    )
    op.add_column("conversation_messages", sa.Column("expires_at", sa.DateTime(timezone=True)))
    op.create_index(
        "ix_conversation_message_channel_history",
        "conversation_messages",
        [
            "tenant_id",
            "im_channel_id",
            "im_agent_binding_id",
            "agent_id",
            "actor_type",
            "actor_id",
            "conversation_id",
            "thread_id",
            "created_at",
        ],
    )
    op.create_unique_constraint(
        "uq_conversation_message_external",
        "conversation_messages",
        ["tenant_id", "im_channel_id", "external_message_id"],
    )
    op.create_unique_constraint(
        "uq_conversation_message_tenant_id",
        "conversation_messages",
        ["tenant_id", "id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_conversation_message_tenant_id", "conversation_messages", type_="unique")
    op.drop_constraint("uq_conversation_message_external", "conversation_messages", type_="unique")
    op.drop_index("ix_conversation_message_channel_history", table_name="conversation_messages")
    for name in (
        "expires_at",
        "delivery_status",
        "provider_message_id",
        "external_message_id",
        "direction",
        "conversation_kind",
        "im_agent_binding_id",
        "im_channel_id",
    ):
        op.drop_column("conversation_messages", name)
    op.drop_column("interactions", "transcript_expires_at")
    op.drop_column("interactions", "conversation_kind")
