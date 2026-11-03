"""Add tenant-level knowledge merge settings.

Revision ID: 0060_knowledge_merge_settings
Revises: 0059_knowledge_multimodal_assets
"""

import sqlalchemy as sa

from alembic import op

revision: str = "0060_knowledge_merge_settings"
down_revision: str | None = "0059_knowledge_multimodal_assets"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "knowledge_merge_settings",
        sa.Column("tenant_id", sa.String(64), primary_key=True),
        sa.Column(
            "merge_rerank_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("reranker_config_id", sa.String(64)),
        sa.Column(
            "rerank_top_n",
            sa.Integer(),
            nullable=False,
            server_default="20",
        ),
        sa.Column(
            "result_top_k",
            sa.Integer(),
            nullable=False,
            server_default="6",
        ),
        sa.Column("min_rerank_score", sa.Float()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "reranker_config_id"],
            ["reranker_configs.tenant_id", "reranker_configs.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "rerank_top_n BETWEEN 1 AND 60",
            name="ck_knowledge_merge_settings_rerank_top_n",
        ),
        sa.CheckConstraint(
            "result_top_k BETWEEN 1 AND 12",
            name="ck_knowledge_merge_settings_result_top_k",
        ),
        sa.CheckConstraint(
            "rerank_top_n >= result_top_k",
            name="ck_knowledge_merge_settings_top_n_gte_top_k",
        ),
        sa.CheckConstraint(
            "min_rerank_score IS NULL OR min_rerank_score BETWEEN 0 AND 1",
            name="ck_knowledge_merge_settings_min_score",
        ),
        sa.CheckConstraint(
            "(merge_rerank_enabled AND reranker_config_id IS NOT NULL) OR "
            "(NOT merge_rerank_enabled AND reranker_config_id IS NULL)",
            name="ck_knowledge_merge_settings_reranker_dependency",
        ),
        sa.CheckConstraint(
            "merge_rerank_enabled OR min_rerank_score IS NULL",
            name="ck_knowledge_merge_settings_score_dependency",
        ),
    )
    op.execute(sa.text("ALTER TABLE knowledge_merge_settings ENABLE ROW LEVEL SECURITY"))
    op.execute(
        sa.text(
            "CREATE POLICY knowledge_merge_settings_tenant_isolation ON knowledge_merge_settings "
            "USING (tenant_id = current_setting('app.current_tenant_id', true)) "
            "WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true))"
        )
    )


def downgrade() -> None:
    raise RuntimeError(
        "Knowledge merge settings are not downgradable; restore a pre-migration backup instead."
    )
