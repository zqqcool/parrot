"""Add durable memory-vector indexing jobs and references.

Revision ID: 0019_memory_vector_indexing
Revises: 0018_runtime_memory_metadata
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0019_memory_vector_indexing"
down_revision: str | None = "0018_runtime_memory_metadata"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint("uq_memory_record_tenant_id", "memory_records", ["tenant_id", "id"])
    _create_index_jobs()
    _create_vector_references()
    for table in ("memory_index_jobs", "memory_vector_references"):
        op.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        op.execute(
            sa.text(
                f"CREATE POLICY {table}_tenant_isolation ON {table} "
                "USING (tenant_id = current_setting('app.current_tenant_id', true)) "
                "WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true))"
            )
        )


def _create_index_jobs() -> None:
    op.create_table(
        "memory_index_jobs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("memory_id", sa.String(64), nullable=False),
        sa.Column("memory_version", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("lease_owner", sa.String(128)),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "memory_id"],
            ["memory_records.tenant_id", "memory_records.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "tenant_id", "memory_id", "memory_version", "action", name="uq_memory_index_job_version"
        ),
    )
    op.create_index(
        "ix_memory_index_job_claim",
        "memory_index_jobs",
        ["tenant_id", "status", "lease_until", "created_at"],
    )


def _create_vector_references() -> None:
    op.create_table(
        "memory_vector_references",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("memory_id", sa.String(64), nullable=False),
        sa.Column("memory_version", sa.Integer(), nullable=False),
        sa.Column("vector_id", sa.String(191), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("collection", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "memory_id"],
            ["memory_records.tenant_id", "memory_records.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("vector_id", name="uq_memory_vector_reference_id"),
    )
    op.create_index(
        "ix_memory_vector_reference_memory",
        "memory_vector_references",
        ["tenant_id", "memory_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_memory_vector_reference_memory", table_name="memory_vector_references")
    op.drop_table("memory_vector_references")
    op.drop_index("ix_memory_index_job_claim", table_name="memory_index_jobs")
    op.drop_table("memory_index_jobs")
    op.drop_constraint("uq_memory_record_tenant_id", "memory_records", type_="unique")
