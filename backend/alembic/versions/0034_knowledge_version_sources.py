"""Link immutable knowledge versions to their private source objects.

Revision ID: 0034_knowledge_version_sources
Revises: 0033_knowledge_chunking_settings
Create Date: 2026-07-15
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0034_knowledge_version_sources"
down_revision: str | None = "0033_knowledge_chunking_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("knowledge_sources", sa.Column("target_document_id", sa.String(64)))
    op.create_foreign_key(
        "fk_knowledge_source_target_document",
        "knowledge_sources",
        "knowledge_documents",
        ["tenant_id", "target_document_id"],
        ["tenant_id", "id"],
        ondelete="RESTRICT",
    )
    op.add_column("knowledge_document_versions", sa.Column("source_id", sa.String(64)))
    op.create_foreign_key(
        "fk_knowledge_version_source",
        "knowledge_document_versions",
        "knowledge_sources",
        ["tenant_id", "source_id"],
        ["tenant_id", "id"],
        ondelete="RESTRICT",
    )
    op.execute(
        sa.text(
            "UPDATE knowledge_document_versions AS version "
            "SET source_id = document.source_id "
            "FROM knowledge_documents AS document "
            "WHERE version.tenant_id = document.tenant_id "
            "AND version.document_id = document.id "
            "AND version.version = 1 "
            "AND document.source_id IS NOT NULL"
        )
    )


def downgrade() -> None:
    raise RuntimeError(
        "Knowledge version source links are not downgradable; restore a database backup."
    )
