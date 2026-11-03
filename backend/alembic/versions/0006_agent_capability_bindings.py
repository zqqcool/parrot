"""Add tenant-safe agent capability bindings.

Revision ID: 0006_agent_capability_bindings
Revises: 0005_agent_capability_catalog
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006_agent_capability_bindings"
down_revision: str | None = "0005_agent_capability_catalog"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint("uq_llm_config_tenant_id", "llm_configs", ["tenant_id", "id"])
    op.create_unique_constraint("uq_skill_tenant_id", "skills", ["tenant_id", "id"])
    op.create_table(
        "agent_llm_config_bindings",
        sa.Column("agent_id", sa.String(64), primary_key=True),
        sa.Column("llm_config_id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(
            ["agent_id", "tenant_id"],
            ["agent_publications.id", "agent_publications.tenant_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["llm_config_id", "tenant_id"],
            ["llm_configs.id", "llm_configs.tenant_id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_agent_llm_binding_tenant_agent",
        "agent_llm_config_bindings",
        ["tenant_id", "agent_id"],
    )
    op.create_index(
        "uq_agent_default_llm",
        "agent_llm_config_bindings",
        ["tenant_id", "agent_id"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )
    op.create_table(
        "agent_skill_bindings",
        sa.Column("agent_id", sa.String(64), primary_key=True),
        sa.Column("skill_id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(
            ["agent_id", "tenant_id"],
            ["agent_publications.id", "agent_publications.tenant_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["skill_id", "tenant_id"],
            ["skills.id", "skills.tenant_id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_agent_skill_binding_tenant_agent",
        "agent_skill_bindings",
        ["tenant_id", "agent_id"],
    )
    for table in ("agent_llm_config_bindings", "agent_skill_bindings"):
        op.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        op.execute(
            sa.text(
                f"CREATE POLICY {table}_tenant_isolation ON {table} "
                "USING (tenant_id = current_setting('app.current_tenant_id', true)) "
                "WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true))"
            )
        )


def downgrade() -> None:
    op.drop_index("ix_agent_skill_binding_tenant_agent", table_name="agent_skill_bindings")
    op.drop_table("agent_skill_bindings")
    op.drop_index("uq_agent_default_llm", table_name="agent_llm_config_bindings")
    op.drop_index("ix_agent_llm_binding_tenant_agent", table_name="agent_llm_config_bindings")
    op.drop_table("agent_llm_config_bindings")
    op.drop_constraint("uq_skill_tenant_id", "skills", type_="unique")
    op.drop_constraint("uq_llm_config_tenant_id", "llm_configs", type_="unique")
