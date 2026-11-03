"""Add tenant-isolated knowledge spaces and PostgreSQL text retrieval.

Revision ID: 0031_knowledge_space_foundation
Revises: 0030_remove_system_capabilities
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0031_knowledge_space_foundation"
down_revision: str | None = "0030_remove_system_capabilities"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    _create_spaces()
    _create_grants()
    _create_documents()
    _create_agent_bindings()
    for table in (
        "knowledge_spaces",
        "knowledge_space_user_grants",
        "knowledge_space_group_grants",
        "knowledge_documents",
        "knowledge_document_versions",
        "knowledge_chunks",
        "agent_knowledge_space_bindings",
    ):
        _enable_tenant_rls(table)


def _create_spaces() -> None:
    op.create_table(
        "knowledge_spaces",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(64),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("classification", sa.String(32), nullable=False, server_default="standard"),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("access_revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_by_user_id",
            sa.String(64),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "slug", name="uq_knowledge_space_tenant_slug"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_knowledge_space_tenant_id"),
    )
    op.create_index("ix_knowledge_space_tenant_status", "knowledge_spaces", ["tenant_id", "status"])


def _create_grants() -> None:
    op.create_table(
        "knowledge_space_user_grants",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("space_id", sa.String(64), nullable=False),
        sa.Column(
            "user_id", sa.String(64), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "space_id"],
            ["knowledge_spaces.tenant_id", "knowledge_spaces.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "tenant_id", "space_id", "user_id", name="uq_knowledge_space_user_grant"
        ),
    )
    op.create_index(
        "ix_knowledge_user_grant_lookup",
        "knowledge_space_user_grants",
        ["tenant_id", "user_id", "space_id"],
    )
    op.create_table(
        "knowledge_space_group_grants",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("space_id", sa.String(64), nullable=False),
        sa.Column("group_id", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "space_id"],
            ["knowledge_spaces.tenant_id", "knowledge_spaces.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "group_id"], ["groups.tenant_id", "groups.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "tenant_id", "space_id", "group_id", name="uq_knowledge_space_group_grant"
        ),
    )
    op.create_index(
        "ix_knowledge_group_grant_lookup",
        "knowledge_space_group_grants",
        ["tenant_id", "group_id", "space_id"],
    )


def _create_documents() -> None:
    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("space_id", sa.String(64), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("source_uri", sa.String(1000)),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
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
        sa.UniqueConstraint("tenant_id", "id", name="uq_knowledge_document_tenant_id"),
    )
    op.create_index(
        "ix_knowledge_document_space_status",
        "knowledge_documents",
        ["tenant_id", "space_id", "status"],
    )
    op.create_table(
        "knowledge_document_versions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("document_id", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="published"),
        sa.Column("extraction_status", sa.String(32), nullable=False, server_default="completed"),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["knowledge_documents.tenant_id", "knowledge_documents.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "tenant_id", "document_id", "version", name="uq_knowledge_document_version"
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_knowledge_document_version_tenant_id"),
    )
    op.create_index(
        "ix_knowledge_version_document_status",
        "knowledge_document_versions",
        ["tenant_id", "document_id", "status"],
    )
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("space_id", sa.String(64), nullable=False),
        sa.Column("document_version_id", sa.String(64), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("citation_anchor", sa.String(191), nullable=False),
        sa.Column("search_vector", postgresql.TSVECTOR(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "space_id"],
            ["knowledge_spaces.tenant_id", "knowledge_spaces.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_version_id"],
            ["knowledge_document_versions.tenant_id", "knowledge_document_versions.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "tenant_id", "document_version_id", "ordinal", name="uq_knowledge_chunk_ordinal"
        ),
    )
    op.create_index(
        "ix_knowledge_chunk_space_version",
        "knowledge_chunks",
        ["tenant_id", "space_id", "document_version_id"],
    )
    op.create_index(
        "ix_knowledge_chunk_search_vector",
        "knowledge_chunks",
        ["search_vector"],
        postgresql_using="gin",
    )


def _create_agent_bindings() -> None:
    op.create_table(
        "agent_knowledge_space_bindings",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("agent_id", sa.String(64), nullable=False),
        sa.Column("space_id", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "agent_id"],
            ["agent_publications.tenant_id", "agent_publications.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "space_id"],
            ["knowledge_spaces.tenant_id", "knowledge_spaces.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("tenant_id", "agent_id", "space_id", name="uq_agent_knowledge_space"),
    )
    op.create_index(
        "ix_agent_knowledge_space_lookup",
        "agent_knowledge_space_bindings",
        ["tenant_id", "agent_id", "space_id"],
    )


def _enable_tenant_rls(table: str) -> None:
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
        "Knowledge-space data is not downgradable; restore a pre-migration backup instead."
    )
