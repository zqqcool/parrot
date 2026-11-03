"""Lock knowledge-space Embedding identities with durable snapshots.

Revision ID: 0038_embedding_snapshots
Revises: 0037_memory_hybrid_retrieval
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0038_embedding_snapshots"
down_revision: str | None = "0037_memory_hybrid_retrieval"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    with op.batch_alter_table("embedding_configs") as batch:
        batch.add_column(
            sa.Column("configuration_version", sa.Integer(), nullable=False, server_default="1")
        )
    with op.batch_alter_table("knowledge_spaces") as batch:
        batch.add_column(sa.Column("embedding_config_provider", sa.String(64)))
        batch.add_column(sa.Column("embedding_config_model", sa.String(128)))
        batch.add_column(sa.Column("embedding_config_base_url", sa.String(512)))
        batch.add_column(sa.Column("embedding_config_dimension", sa.Integer()))
        batch.add_column(sa.Column("embedding_config_version", sa.Integer()))
    op.execute(
        sa.text(
            "UPDATE knowledge_spaces AS space "
            "SET embedding_config_provider = config.provider, "
            "embedding_config_model = config.model, "
            "embedding_config_base_url = config.base_url, "
            "embedding_config_dimension = config.embedding_dimension, "
            "embedding_config_version = config.configuration_version "
            "FROM embedding_configs AS config "
            "WHERE space.tenant_id = config.tenant_id "
            "AND space.embedding_config_id = config.id"
        )
    )


def downgrade() -> None:
    raise RuntimeError(
        "Knowledge Embedding snapshots are not downgradable; restore a database backup."
    )
