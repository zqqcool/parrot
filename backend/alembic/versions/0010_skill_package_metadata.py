"""Persist tenant-owned Skill package metadata.

Revision ID: 0010_skill_package_metadata
Revises: 0009_agent_avatar_storage
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010_skill_package_metadata"
down_revision: str | None = "0009_agent_avatar_storage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("skills", sa.Column("package_path", sa.String(length=512), nullable=True))
    op.add_column("skills", sa.Column("package_filename", sa.String(length=255), nullable=True))
    op.add_column("skills", sa.Column("package_size_bytes", sa.BigInteger(), nullable=True))
    op.add_column("skills", sa.Column("package_sha256", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("skills", "package_sha256")
    op.drop_column("skills", "package_size_bytes")
    op.drop_column("skills", "package_filename")
    op.drop_column("skills", "package_path")
