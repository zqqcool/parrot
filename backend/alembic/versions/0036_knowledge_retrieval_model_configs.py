"""Add tenant model configurations and knowledge retrieval policy.

Revision ID: 0036_retrieval_model_configs
Revises: 0035_knowledge_vector_index
Create Date: 2026-07-15
"""

from collections.abc import Iterable, Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0036_retrieval_model_configs"
down_revision: str | None = "0035_knowledge_vector_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    _create_embedding_configs()
    _create_reranker_configs()
    _add_knowledge_space_policy()
    _version_vector_outbox()
    _retire_legacy_vector_jobs()
    _enable_tenant_rls(("embedding_configs", "reranker_configs"))


def _create_embedding_configs() -> None:
    op.create_table(
        "embedding_configs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(64),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("base_url", sa.String(512), nullable=False),
        sa.Column("credential_envelope", sa.Text()),
        sa.Column("embedding_dimension", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "name", name="uq_embedding_config_tenant_name"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_embedding_config_tenant_id"),
    )
    op.create_index(
        "ix_embedding_config_tenant_status", "embedding_configs", ["tenant_id", "status"]
    )


def _create_reranker_configs() -> None:
    op.create_table(
        "reranker_configs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(64),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("base_url", sa.String(512), nullable=False),
        sa.Column("credential_envelope", sa.Text()),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "name", name="uq_reranker_config_tenant_name"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_reranker_config_tenant_id"),
    )
    op.create_index("ix_reranker_config_tenant_status", "reranker_configs", ["tenant_id", "status"])


def _add_knowledge_space_policy() -> None:
    with op.batch_alter_table("knowledge_spaces") as batch:
        batch.add_column(sa.Column("embedding_config_id", sa.String(64)))
        batch.add_column(
            sa.Column("candidate_top_k", sa.Integer(), nullable=False, server_default="20")
        )
        batch.add_column(sa.Column("min_vector_score", sa.Float()))
        batch.add_column(
            sa.Column("rerank_enabled", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch.add_column(sa.Column("reranker_config_id", sa.String(64)))
        batch.add_column(
            sa.Column("rerank_top_n", sa.Integer(), nullable=False, server_default="10")
        )
        batch.add_column(sa.Column("min_rerank_score", sa.Float()))
        batch.add_column(
            sa.Column(
                "allow_external_processing", sa.Boolean(), nullable=False, server_default=sa.false()
            )
        )
        batch.add_column(
            sa.Column("retrieval_index_revision", sa.Integer(), nullable=False, server_default="1")
        )
        batch.add_column(
            sa.Column(
                "retrieval_index_status",
                sa.String(32),
                nullable=False,
                server_default="not_configured",
            )
        )
        batch.create_foreign_key(
            "fk_knowledge_space_embedding_config",
            "embedding_configs",
            ["tenant_id", "embedding_config_id"],
            ["tenant_id", "id"],
            ondelete="RESTRICT",
        )
        batch.create_foreign_key(
            "fk_knowledge_space_reranker_config",
            "reranker_configs",
            ["tenant_id", "reranker_config_id"],
            ["tenant_id", "id"],
            ondelete="RESTRICT",
        )


def _version_vector_outbox() -> None:
    with op.batch_alter_table("knowledge_vector_index_jobs") as batch:
        batch.drop_constraint("uq_knowledge_vector_job_version", type_="unique")
        batch.add_column(sa.Column("embedding_config_id", sa.String(64)))
        batch.add_column(
            sa.Column("index_revision", sa.Integer(), nullable=False, server_default="1")
        )
        batch.create_foreign_key(
            "fk_knowledge_vector_job_embedding_config",
            "embedding_configs",
            ["tenant_id", "embedding_config_id"],
            ["tenant_id", "id"],
            ondelete="RESTRICT",
        )
        batch.create_unique_constraint(
            "uq_knowledge_vector_job_profile_version",
            ["tenant_id", "document_version_id", "embedding_config_id", "index_revision", "action"],
        )
    with op.batch_alter_table("knowledge_vector_references") as batch:
        batch.add_column(sa.Column("embedding_config_id", sa.String(64)))
        batch.add_column(
            sa.Column("index_revision", sa.Integer(), nullable=False, server_default="1")
        )
        batch.create_foreign_key(
            "fk_knowledge_vector_reference_embedding_config",
            "embedding_configs",
            ["tenant_id", "embedding_config_id"],
            ["tenant_id", "id"],
            ondelete="RESTRICT",
        )
    op.create_index(
        "ix_knowledge_vector_reference_profile_version",
        "knowledge_vector_references",
        ["tenant_id", "embedding_config_id", "index_revision", "document_version_id"],
    )


def _retire_legacy_vector_jobs() -> None:
    """Do not let pre-policy jobs send historical content to a legacy provider."""
    op.execute(
        sa.text(
            "UPDATE knowledge_vector_index_jobs "
            "SET status = 'succeeded', error_code = 'RETIRED_BY_RETRIEVAL_POLICY', "
            "lease_owner = NULL, lease_until = NULL "
            "WHERE embedding_config_id IS NULL AND status IN ('queued', 'running')"
        )
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
        "Knowledge retrieval configuration is not downgradable; restore a database backup."
    )
