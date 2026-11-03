"""Add versioned knowledge chunk separators.

Revision ID: 0044_knowledge_chunk_separator
Revises: 0043_knowledge_text_processing
Create Date: 2026-07-16
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0044_knowledge_chunk_separator"
down_revision: str | None = "0043_knowledge_text_processing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    for table in ("knowledge_spaces", "knowledge_document_versions"):
        op.add_column(
            table,
            sa.Column("chunk_separator", sa.String(128), nullable=False, server_default=r"\n\n"),
        )


def downgrade() -> None:
    raise RuntimeError(
        "Knowledge chunk-separator settings are not downgradable; restore a database backup."
    )
