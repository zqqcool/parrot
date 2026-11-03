"""Persist managed user-avatar object metadata.

Revision ID: 0029_user_avatar_storage
Revises: 0028_agent_single_llm_binding
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0029_user_avatar_storage"
down_revision: str | None = "0028_agent_single_llm_binding"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("avatar_key", sa.String(length=256), nullable=True))
    op.add_column("users", sa.Column("avatar_content_type", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "avatar_content_type")
    op.drop_column("users", "avatar_key")
