"""Add immutable Skill versions and mutable draft pointers.

Revision ID: 0014_skill_version_workbench
Revises: 0013_agent_type_default
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0014_skill_version_workbench"
down_revision: str | None = "0013_agent_type_default"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("skills", sa.Column("current_version_id", sa.String(length=64), nullable=True))
    op.add_column("skills", sa.Column("draft_version_id", sa.String(length=64), nullable=True))
    op.create_table(
        "skill_versions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("skill_id", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("manifest", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False, server_default=""),
        sa.Column("package_path", sa.String(length=512), nullable=True),
        sa.Column("package_filename", sa.String(length=255), nullable=True),
        sa.Column("package_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("package_sha256", sa.String(length=64), nullable=True),
        sa.Column("source_version_id", sa.String(length=64), nullable=True),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.Column("published_by", sa.String(length=64), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "skill_id", "version", name="uq_skill_version_sequence"),
    )
    op.create_index(
        "ix_skill_version_tenant_skill_status",
        "skill_versions",
        ["tenant_id", "skill_id", "status"],
    )
    op.execute(
        sa.text(
            """
            INSERT INTO skill_versions (
                id, tenant_id, skill_id, version, status, description, manifest, instructions,
                package_path, package_filename, package_size_bytes, package_sha256,
                created_at, updated_at, published_at
            )
            SELECT
                'skill_version_' || substr(md5(id), 1, 24),
                tenant_id,
                id,
                version,
                CASE WHEN status = 'draft' THEN 'draft' ELSE 'published' END,
                description,
                manifest,
                instructions,
                package_path,
                package_filename,
                package_size_bytes,
                package_sha256,
                created_at,
                updated_at,
                CASE WHEN status = 'draft' THEN NULL ELSE updated_at END
            FROM skills
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE skills AS skill
            SET
                current_version_id = CASE
                    WHEN skill.status = 'draft' THEN NULL
                    ELSE version.id
                END,
                draft_version_id = CASE
                    WHEN skill.status = 'draft' THEN version.id
                    ELSE NULL
                END
            FROM skill_versions AS version
            WHERE version.skill_id = skill.id
              AND version.tenant_id = skill.tenant_id
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_skill_version_tenant_skill_status", table_name="skill_versions")
    op.drop_table("skill_versions")
    op.drop_column("skills", "draft_version_id")
    op.drop_column("skills", "current_version_id")
