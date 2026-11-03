"""Add durable system capability hybrid-index state.

Revision ID: 0052_capability_hybrid_index
Revises: 0051_finalization_candidates
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0052_capability_hybrid_index"
down_revision: str | None = "0051_finalization_candidates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_ID = "NULLIF(current_setting('app.current_tenant_id', true), '')"


def upgrade() -> None:
    op.create_table(
        "capability_index_jobs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("source_kind", sa.String(length=16), nullable=False),
        sa.Column("source_id", sa.String(length=191), nullable=False),
        sa.Column("source_revision", sa.String(length=64), nullable=False),
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default=sa.text("'queued'")
        ),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("lease_owner", sa.String(length=128)),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(length=128)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "tenant_id",
            "source_kind",
            "source_id",
            "source_revision",
            name="uq_capability_index_job_source_revision",
        ),
    )
    op.create_index(
        "ix_capability_index_job_claim",
        "capability_index_jobs",
        ["tenant_id", "status", "lease_until", "created_at"],
    )
    op.create_table(
        "capability_vector_references",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("source_kind", sa.String(length=16), nullable=False),
        sa.Column("source_id", sa.String(length=191), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("source_revision", sa.String(length=64), nullable=False),
        sa.Column("vector_id", sa.String(length=191), nullable=False),
        sa.Column("collection", sa.String(length=128), nullable=False),
        sa.Column("content_digest", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "tenant_id", "source_kind", "source_id", name="uq_capability_vector_source"
        ),
        sa.UniqueConstraint("vector_id", name="uq_capability_vector_id"),
    )
    op.create_index(
        "ix_capability_vector_reference_owner",
        "capability_vector_references",
        ["tenant_id", "owner_id"],
    )
    for table in ("capability_index_jobs", "capability_vector_references"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_tenant_access ON {table} "
            f"FOR ALL USING (tenant_id = {TENANT_ID}) WITH CHECK (tenant_id = {TENANT_ID})"
        )


def downgrade() -> None:
    for table in ("capability_vector_references", "capability_index_jobs"):
        op.execute(f"DROP POLICY {table}_tenant_access ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_capability_vector_reference_owner", table_name="capability_vector_references")
    op.drop_table("capability_vector_references")
    op.drop_index("ix_capability_index_job_claim", table_name="capability_index_jobs")
    op.drop_table("capability_index_jobs")
