"""Add a durable, independently replaceable knowledge vector index.

Revision ID: 0035_knowledge_vector_index
Revises: 0034_knowledge_version_sources
Create Date: 2026-07-15
"""

from collections.abc import Iterable, Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0035_knowledge_vector_index"
down_revision: str | None = "0034_knowledge_version_sources"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_knowledge_chunk_tenant_id", "knowledge_chunks", ["tenant_id", "id"]
    )
    _create_index_jobs()
    _create_vector_references()
    _enable_tenant_rls(("knowledge_vector_index_jobs", "knowledge_vector_references"))


def _create_index_jobs() -> None:
    op.create_table(
        "knowledge_vector_index_jobs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("document_version_id", sa.String(64), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lease_owner", sa.String(128)),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_version_id"],
            ["knowledge_document_versions.tenant_id", "knowledge_document_versions.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "document_version_id",
            "action",
            name="uq_knowledge_vector_job_version",
        ),
    )
    op.create_index(
        "ix_knowledge_vector_job_claim",
        "knowledge_vector_index_jobs",
        ["tenant_id", "status", "lease_until", "created_at"],
    )


def _create_vector_references() -> None:
    op.create_table(
        "knowledge_vector_references",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("document_version_id", sa.String(64), nullable=False),
        sa.Column("chunk_id", sa.String(64), nullable=False),
        sa.Column("vector_id", sa.String(191), nullable=False),
        sa.Column("collection", sa.String(128), nullable=False),
        sa.Column("embedding_model", sa.String(191), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "chunk_id"],
            ["knowledge_chunks.tenant_id", "knowledge_chunks.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_version_id"],
            ["knowledge_document_versions.tenant_id", "knowledge_document_versions.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("vector_id", name="uq_knowledge_vector_reference_id"),
    )
    op.create_index(
        "ix_knowledge_vector_reference_version",
        "knowledge_vector_references",
        ["tenant_id", "document_version_id"],
    )


def _enable_tenant_rls(tables: Iterable[str]) -> None:
    for table in tables:
        op.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        op.execute(
            sa.text(
                f"CREATE POLICY {table}_tenant_isolation ON {table} "
                "USING (tenant_id = current_setting('app.current_tenant_id', true)) "
                "WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true))"
            )
        )


def downgrade() -> None:
    raise RuntimeError("Knowledge vector state is not downgradable; restore a database backup.")
