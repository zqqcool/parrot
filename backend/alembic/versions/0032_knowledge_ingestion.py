"""Add private knowledge sources and durable ingestion jobs.

Revision ID: 0032_knowledge_ingestion
Revises: 0031_knowledge_space_foundation
Create Date: 2026-07-14
"""

from collections.abc import Iterable

import sqlalchemy as sa

from alembic import op

revision: str = "0032_knowledge_ingestion"
down_revision: str | None = "0031_knowledge_space_foundation"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    _create_sources()
    _extend_documents()
    _create_jobs()
    _enable_tenant_rls(("knowledge_sources", "knowledge_ingestion_jobs"))


def _create_sources() -> None:
    op.create_table(
        "knowledge_sources",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("space_id", sa.String(64), nullable=False),
        sa.Column("source_kind", sa.String(32), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("original_filename", sa.String(300), nullable=False),
        sa.Column("content_type", sa.String(128), nullable=False),
        sa.Column("declared_size_bytes", sa.Integer(), nullable=False),
        sa.Column("content_sha256", sa.String(64)),
        sa.Column("staging_key", sa.String(512)),
        sa.Column("object_key", sa.String(512)),
        sa.Column("status", sa.String(32), nullable=False, server_default="staging"),
        sa.Column(
            "created_by_user_id",
            sa.String(64),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "space_id"],
            ["knowledge_spaces.tenant_id", "knowledge_spaces.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_knowledge_source_tenant_id"),
    )
    op.create_index(
        "ix_knowledge_source_space_status", "knowledge_sources", ["tenant_id", "space_id", "status"]
    )


def _extend_documents() -> None:
    op.add_column("knowledge_documents", sa.Column("source_id", sa.String(64)))
    op.create_foreign_key(
        "fk_knowledge_document_source",
        "knowledge_documents",
        "knowledge_sources",
        ["tenant_id", "source_id"],
        ["tenant_id", "id"],
        ondelete="RESTRICT",
    )
    op.add_column(
        "knowledge_document_versions", sa.Column("published_at", sa.DateTime(timezone=True))
    )


def _create_jobs() -> None:
    op.create_table(
        "knowledge_ingestion_jobs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("source_id", sa.String(64), nullable=False),
        sa.Column("document_version_id", sa.String(64), nullable=False),
        sa.Column("action", sa.String(32), nullable=False, server_default="extract"),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lease_owner", sa.String(128)),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "source_id"],
            ["knowledge_sources.tenant_id", "knowledge_sources.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_version_id"],
            ["knowledge_document_versions.tenant_id", "knowledge_document_versions.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "source_id",
            "document_version_id",
            "action",
            name="uq_knowledge_ingestion_job_version",
        ),
    )
    op.create_index(
        "ix_knowledge_ingestion_job_claim",
        "knowledge_ingestion_jobs",
        ["tenant_id", "status", "lease_until", "created_at"],
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
    raise RuntimeError(
        "Knowledge-ingestion data is not downgradable; restore a pre-migration backup instead."
    )
