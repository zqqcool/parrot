"""Add PostgreSQL full-text and chronology indexes for runtime memory retrieval.

Revision ID: 0037_memory_hybrid_retrieval
Revises: 0036_retrieval_model_configs
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0037_memory_hybrid_retrieval"
down_revision: str | None = "0036_retrieval_model_configs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "memory_records",
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(
                "to_tsvector('simple', coalesce(key, '') || ' ' || coalesce(content, ''))",
                persisted=True,
            ),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_memory_search_vector",
        "memory_records",
        ["search_vector"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_memory_scope_chronology",
        "memory_records",
        ["tenant_id", "agent_id", "scope_type", "scope_id", "created_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_memory_scope_chronology", table_name="memory_records")
    op.drop_index("ix_memory_search_vector", table_name="memory_records")
    op.drop_column("memory_records", "search_vector")
