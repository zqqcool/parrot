"""Remove legacy group and thread conversation semantics.

Revision ID: 0045_p2p_only_conversations
Revises: 0044_knowledge_chunk_separator
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0045_p2p_only_conversations"
down_revision: str | None = "0044_knowledge_chunk_separator"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    _reject_legacy_conversation_data()
    op.drop_index("ix_interactions_thread_id", table_name="interactions")
    op.drop_column("interactions", "conversation_kind")
    op.drop_column("interactions", "thread_id")
    op.drop_index("ix_conversation_message_history", table_name="conversation_messages")
    op.drop_index("ix_conversation_message_channel_history", table_name="conversation_messages")
    op.drop_column("conversation_messages", "conversation_kind")
    op.drop_column("conversation_messages", "thread_id")
    op.create_index(
        "ix_conversation_message_history",
        "conversation_messages",
        ["tenant_id", "agent_id", "actor_type", "actor_id", "conversation_id", "created_at"],
    )
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
            "created_at",
        ],
    )
    op.drop_column("memory_records", "thread_id")


def downgrade() -> None:
    raise RuntimeError(
        "P2P-only conversation cleanup is not downgradable; restore a database backup."
    )


def _reject_legacy_conversation_data() -> None:
    connection = op.get_bind()
    checks = {
        "non_p2p_interactions": """
            SELECT count(*) FROM interactions WHERE conversation_kind <> 'p2p'
        """,
        "threaded_interactions": """
            SELECT count(*) FROM interactions WHERE thread_id IS NOT NULL
        """,
        "non_p2p_messages": """
            SELECT count(*) FROM conversation_messages WHERE conversation_kind <> 'p2p'
        """,
        "threaded_messages": """
            SELECT count(*) FROM conversation_messages WHERE thread_id IS NOT NULL
        """,
        "thread_memory": """
            SELECT count(*) FROM memory_records
            WHERE thread_id IS NOT NULL OR scope_type = 'thread'
        """,
        "thread_summaries": """
            SELECT count(*) FROM memory_records WHERE memory_type = 'thread_summary'
        """,
    }
    findings = {
        name: int(connection.execute(sa.text(query)).scalar_one())
        for name, query in checks.items()
    }
    legacy = {name: count for name, count in findings.items() if count}
    if legacy:
        details = ", ".join(f"{name}={count}" for name, count in sorted(legacy.items()))
        raise RuntimeError(
            "P2P-only migration blocked by legacy group or thread data: "
            f"{details}. Export or remediate those records before retrying."
        )
