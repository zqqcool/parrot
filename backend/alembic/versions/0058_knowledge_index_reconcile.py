"""Reconcile knowledge index status within each space.

Revision ID: 0058_knowledge_index_reconcile
Revises: 0057_llm_prompt_cache
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0058_knowledge_index_reconcile"
down_revision: str | None = "0057_llm_prompt_cache"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            WITH index_states AS (
                SELECT
                    space.tenant_id,
                    space.id AS space_id,
                    bool_or(job.status = 'failed') AS has_failed,
                    bool_or(job.status IN ('queued', 'running')) AS has_pending
                FROM knowledge_spaces AS space
                JOIN knowledge_documents AS document
                  ON document.tenant_id = space.tenant_id
                 AND document.space_id = space.id
                JOIN knowledge_document_versions AS version
                  ON version.tenant_id = document.tenant_id
                 AND version.document_id = document.id
                JOIN knowledge_vector_index_jobs AS job
                  ON job.tenant_id = version.tenant_id
                 AND job.document_version_id = version.id
                 AND job.embedding_config_id = space.embedding_config_id
                 AND job.index_revision = space.retrieval_index_revision
                WHERE space.embedding_config_id IS NOT NULL
                GROUP BY space.tenant_id, space.id
            )
            UPDATE knowledge_spaces AS space
            SET retrieval_index_status = CASE
                WHEN state.has_failed THEN 'failed'
                WHEN state.has_pending THEN 'pending'
                ELSE 'ready'
            END
            FROM index_states AS state
            WHERE space.tenant_id = state.tenant_id
              AND space.id = state.space_id
            """
        )
    )


def downgrade() -> None:
    raise RuntimeError("Knowledge index-status reconciliation is not reversible; restore a backup.")
