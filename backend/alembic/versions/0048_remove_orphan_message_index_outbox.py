"""Remove the unconsumed raw-message indexing outbox.

Revision ID: 0048_remove_message_index_outbox
Revises: 0047_knowledge_title_identity
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0048_remove_message_index_outbox"
down_revision: str | Sequence[str] | None = "0047_knowledge_title_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.drop_index(
        "ix_message_vector_reference_message", table_name="conversation_message_vector_references"
    )
    op.drop_table("conversation_message_vector_references")
    op.drop_index("ix_message_index_job_claim", table_name="conversation_message_index_jobs")
    op.drop_table("conversation_message_index_jobs")


def downgrade() -> None:
    raise RuntimeError("Restoring the retired unconsumed message queue is unsupported")
