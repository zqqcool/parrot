"""Index expired knowledge upload discovery.

Revision ID: 0061_knowledge_staging_cleanup
Revises: 0060_knowledge_merge_settings
"""

from alembic import op

revision: str = "0061_knowledge_staging_cleanup"
down_revision: str | None = "0060_knowledge_merge_settings"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_index(
        "ix_knowledge_source_staging_cleanup",
        "knowledge_sources",
        ["status", "created_at"],
    )


def downgrade() -> None:
    raise RuntimeError(
        "Knowledge staging cleanup is not downgradable; restore a pre-migration backup instead."
    )
