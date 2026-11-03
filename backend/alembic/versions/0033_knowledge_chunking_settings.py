"""Add versioned knowledge chunking settings.

Revision ID: 0033_knowledge_chunking_settings
Revises: 0032_knowledge_ingestion
Create Date: 2026-07-15
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0033_knowledge_chunking_settings"
down_revision: str | None = "0032_knowledge_ingestion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    _add_space_settings()
    _add_version_snapshots()


def _add_space_settings() -> None:
    op.add_column(
        "knowledge_spaces",
        sa.Column("chunk_size_chars", sa.Integer(), nullable=False, server_default="4000"),
    )
    op.add_column(
        "knowledge_spaces",
        sa.Column("chunk_overlap_chars", sa.Integer(), nullable=False, server_default="200"),
    )
    op.create_check_constraint(
        "ck_knowledge_space_chunking_bounds",
        "knowledge_spaces",
        "chunk_size_chars BETWEEN 500 AND 12000 "
        "AND chunk_overlap_chars >= 0 "
        "AND chunk_overlap_chars < chunk_size_chars",
    )


def _add_version_snapshots() -> None:
    op.add_column(
        "knowledge_document_versions",
        sa.Column("chunk_size_chars", sa.Integer(), nullable=False, server_default="4000"),
    )
    op.add_column(
        "knowledge_document_versions",
        sa.Column("chunk_overlap_chars", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_check_constraint(
        "ck_knowledge_version_chunking_bounds",
        "knowledge_document_versions",
        "chunk_size_chars BETWEEN 500 AND 12000 "
        "AND chunk_overlap_chars >= 0 "
        "AND chunk_overlap_chars < chunk_size_chars",
    )


def downgrade() -> None:
    raise RuntimeError(
        "Knowledge chunking settings are not downgradable; restore a database backup."
    )
