"""Add versioned knowledge text-processing settings.

Revision ID: 0043_knowledge_text_processing
Revises: 0042_restrict_bound_skill_deletion
Create Date: 2026-07-16
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0043_knowledge_text_processing"
down_revision: str | None = "0042_skill_delete_restrict"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    for table in ("knowledge_spaces", "knowledge_document_versions"):
        op.add_column(
            table,
            sa.Column(
                "normalize_whitespace", sa.Boolean(), nullable=False, server_default=sa.false()
            ),
        )
        op.add_column(
            table,
            sa.Column(
                "remove_urls_and_emails", sa.Boolean(), nullable=False, server_default=sa.false()
            ),
        )


def downgrade() -> None:
    raise RuntimeError(
        "Knowledge text-processing settings are not downgradable; restore a database backup."
    )
