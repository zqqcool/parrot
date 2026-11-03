"""Correct pending knowledge-vector index state.

Revision ID: 0046_knowledge_index_state
Revises: 0045_p2p_only_conversations
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0046_knowledge_index_state"
down_revision: str | None = "0045_p2p_only_conversations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE knowledge_spaces AS space
            SET retrieval_index_status = 'pending'
            WHERE space.embedding_config_id IS NOT NULL
              AND space.retrieval_index_status = 'ready'
              AND EXISTS (
                  SELECT 1
                  FROM knowledge_documents AS document
                  JOIN knowledge_document_versions AS version
                    ON version.tenant_id = document.tenant_id
                   AND version.document_id = document.id
                  JOIN knowledge_vector_index_jobs AS job
                    ON job.tenant_id = version.tenant_id
                   AND job.document_version_id = version.id
                   AND job.embedding_config_id = space.embedding_config_id
                   AND job.index_revision = space.retrieval_index_revision
                  WHERE document.tenant_id = space.tenant_id
                    AND document.space_id = space.id
                    AND job.status IN ('queued', 'running')
              )
            """
        )
    )


def downgrade() -> None:
    raise RuntimeError("Knowledge index-state correction is not downgradable; restore a backup.")
