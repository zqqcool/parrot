"""Add knowledge evidence groups, media assets, and locator fields.

Revision ID: 0059_knowledge_multimodal_assets
Revises: 0058_knowledge_index_reconcile
"""

from collections.abc import Iterable

import sqlalchemy as sa

from alembic import op

revision: str = "0059_knowledge_multimodal_assets"
down_revision: str | None = "0058_knowledge_index_reconcile"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    _extend_versions()
    _create_evidence_groups()
    _create_media_assets()
    _extend_chunks()
    _enable_tenant_rls(("knowledge_evidence_groups", "knowledge_media_assets"))


def _extend_versions() -> None:
    op.add_column(
        "knowledge_document_versions",
        sa.Column("format_profile", sa.String(32), nullable=False, server_default="plain_text"),
    )
    op.add_column(
        "knowledge_document_versions",
        sa.Column("extractor_name", sa.String(64)),
    )
    op.add_column(
        "knowledge_document_versions",
        sa.Column("extractor_version", sa.String(32)),
    )
    op.add_column(
        "knowledge_document_versions",
        sa.Column("slide_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "knowledge_document_versions",
        sa.Column("sheet_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "knowledge_document_versions",
        sa.Column("section_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "knowledge_document_versions",
        sa.Column("media_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "knowledge_document_versions",
        sa.Column("skipped_media_count", sa.Integer(), nullable=False, server_default="0"),
    )


def _create_evidence_groups() -> None:
    op.create_table(
        "knowledge_evidence_groups",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("space_id", sa.String(64), nullable=False),
        sa.Column("document_version_id", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("title", sa.String(300), nullable=False, server_default=""),
        sa.Column("expand_default", sa.String(32), nullable=False, server_default="adjacent_1"),
        sa.Column("ordinal_start", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ordinal_end", sa.Integer(), nullable=False, server_default="0"),
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
        sa.UniqueConstraint("tenant_id", "id", name="uq_knowledge_evidence_group_tenant_id"),
        sa.Index(
            "ix_knowledge_evidence_group_version",
            "tenant_id",
            "document_version_id",
        ),
    )


def _create_media_assets() -> None:
    op.create_table(
        "knowledge_media_assets",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("space_id", sa.String(64), nullable=False),
        sa.Column("document_version_id", sa.String(64), nullable=False),
        sa.Column("group_id", sa.String(64)),
        sa.Column("asset_kind", sa.String(32), nullable=False),
        sa.Column("object_key", sa.String(512), nullable=False),
        sa.Column("content_type", sa.String(128), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer()),
        sa.Column("height", sa.Integer()),
        sa.Column("slide_no", sa.Integer()),
        sa.Column("sheet_name", sa.String(191)),
        sa.Column("cell_anchor", sa.String(64)),
        sa.Column("section_path", sa.String(512)),
        sa.Column("ordinal_in_group", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(32), nullable=False, server_default="ready"),
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
        sa.ForeignKeyConstraint(
            ["tenant_id", "group_id"],
            ["knowledge_evidence_groups.tenant_id", "knowledge_evidence_groups.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_knowledge_media_asset_tenant_id"),
        sa.Index(
            "ix_knowledge_media_asset_version",
            "tenant_id",
            "document_version_id",
        ),
        sa.Index(
            "ix_knowledge_media_asset_group",
            "tenant_id",
            "group_id",
            "ordinal_in_group",
        ),
    )


def _extend_chunks() -> None:
    op.add_column("knowledge_chunks", sa.Column("group_id", sa.String(64)))
    op.add_column(
        "knowledge_chunks",
        sa.Column("format_profile", sa.String(32), nullable=False, server_default="plain_text"),
    )
    op.add_column("knowledge_chunks", sa.Column("block_kind", sa.String(32)))
    op.add_column("knowledge_chunks", sa.Column("page_kind", sa.String(32)))
    op.add_column("knowledge_chunks", sa.Column("slide_no", sa.Integer()))
    op.add_column("knowledge_chunks", sa.Column("sheet_name", sa.String(191)))
    op.add_column("knowledge_chunks", sa.Column("section_path", sa.String(512)))
    op.add_column("knowledge_chunks", sa.Column("step_label", sa.String(191)))
    op.add_column("knowledge_chunks", sa.Column("cell_anchor", sa.String(64)))
    op.create_foreign_key(
        "fk_knowledge_chunk_evidence_group",
        "knowledge_chunks",
        "knowledge_evidence_groups",
        ["tenant_id", "group_id"],
        ["tenant_id", "id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_knowledge_chunk_group",
        "knowledge_chunks",
        ["tenant_id", "group_id", "ordinal"],
    )
    op.create_index(
        "ix_knowledge_chunk_slide",
        "knowledge_chunks",
        ["tenant_id", "document_version_id", "slide_no"],
    )


def _enable_tenant_rls(tables: Iterable[str]) -> None:
    for table in tables:
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
        "Knowledge multimodal assets are not downgradable; restore a pre-migration backup instead."
    )
