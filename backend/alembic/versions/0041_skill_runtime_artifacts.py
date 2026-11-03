"""Add immutable Skill build artifacts and durable build jobs.

Revision ID: 0041_skill_artifacts
Revises: 0040_message_index_outbox
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0041_skill_artifacts"
down_revision: str | Sequence[str] | None = "0040_message_index_outbox"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    for table in ("skills", "skill_versions"):
        op.add_column(table, sa.Column("runtime_artifact_path", sa.String(length=512)))
        op.add_column(table, sa.Column("runtime_artifact_sha256", sa.String(length=64)))
        op.add_column(table, sa.Column("runtime_artifact_size_bytes", sa.BigInteger()))
        op.add_column(table, sa.Column("build_status", sa.String(length=16)))
        op.add_column(table, sa.Column("build_source_checksum", sa.String(length=64)))
    op.create_table(
        "skill_build_jobs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("skill_version_id", sa.String(length=64), nullable=False),
        sa.Column("source_checksum", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="queued"),
        sa.Column("lease_owner", sa.String(length=128)),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(length=128)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["skill_version_id"], ["skill_versions.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "tenant_id", "skill_version_id", "source_checksum", name="uq_skill_build_source"
        ),
    )
    op.create_index(
        "ix_skill_build_job_claim",
        "skill_build_jobs",
        ["tenant_id", "status", "lease_until", "created_at"],
    )
    op.execute(sa.text("ALTER TABLE skill_build_jobs ENABLE ROW LEVEL SECURITY"))
    op.execute(
        sa.text(
            "CREATE POLICY skill_build_jobs_tenant_isolation ON skill_build_jobs "
            "USING (tenant_id = current_setting('app.current_tenant_id', true)) "
            "WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true))"
        )
    )


def downgrade() -> None:
    op.drop_index("ix_skill_build_job_claim", table_name="skill_build_jobs")
    op.drop_table("skill_build_jobs")
    for table in ("skill_versions", "skills"):
        for column in (
            "build_source_checksum",
            "build_status",
            "runtime_artifact_size_bytes",
            "runtime_artifact_sha256",
            "runtime_artifact_path",
        ):
            op.drop_column(table, column)
