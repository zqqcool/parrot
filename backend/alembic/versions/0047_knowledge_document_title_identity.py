"""Enforce one available document title per knowledge space.

Revision ID: 0047_knowledge_title_identity
Revises: 0046_knowledge_index_state
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0047_knowledge_title_identity"
down_revision: str | None = "0046_knowledge_index_state"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("knowledge_documents", sa.Column("title_key", sa.String(length=300)))
    op.execute(
        sa.text(
            """
            UPDATE knowledge_documents
            SET title_key = lower(regexp_replace(btrim(title), '[[:space:]]+', ' ', 'g'))
            """
        )
    )
    _reject_duplicate_available_titles()
    op.alter_column("knowledge_documents", "title_key", nullable=False)
    op.create_index(
        "uq_knowledge_document_available_title",
        "knowledge_documents",
        ["tenant_id", "space_id", "title_key"],
        unique=True,
        postgresql_where=sa.text("status IN ('active', 'processing')"),
    )

    op.add_column(
        "knowledge_document_versions",
        sa.Column("created_by_user_id", sa.String(length=64)),
    )
    op.execute(
        sa.text(
            """
            UPDATE knowledge_document_versions AS version
            SET created_by_user_id = coalesce(
                (
                    SELECT source.created_by_user_id
                    FROM knowledge_sources AS source
                    WHERE source.tenant_id = version.tenant_id
                      AND source.id = version.source_id
                ),
                (
                    SELECT document.created_by_user_id
                    FROM knowledge_documents AS document
                    WHERE document.tenant_id = version.tenant_id
                      AND document.id = version.document_id
                )
            )
            """
        )
    )
    op.alter_column("knowledge_document_versions", "created_by_user_id", nullable=False)
    op.create_foreign_key(
        "fk_knowledge_document_version_created_by_user",
        "knowledge_document_versions",
        "users",
        ["created_by_user_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    raise RuntimeError(
        "Knowledge document title identity is not downgradable; restore a database backup."
    )


def _reject_duplicate_available_titles() -> None:
    rows = (
        op.get_bind()
        .execute(
            sa.text(
                """
            SELECT tenant_id, space_id, title_key, string_agg(id, ', ' ORDER BY id) AS document_ids
            FROM knowledge_documents
            WHERE status IN ('active', 'processing')
            GROUP BY tenant_id, space_id, title_key
            HAVING count(*) > 1
            ORDER BY tenant_id, space_id, title_key
            LIMIT 10
            """
            )
        )
        .mappings()
    )
    duplicates = list(rows)
    if not duplicates:
        return
    examples = "; ".join(
        f"tenant={row['tenant_id']}, space={row['space_id']}, title={row['title_key']!r}, "
        f"documents={row['document_ids']}"
        for row in duplicates
    )
    raise RuntimeError(
        "Knowledge title uniqueness migration blocked by duplicate available documents. "
        "Choose the canonical document and archive the others before retrying: "
        f"{examples}"
    )
