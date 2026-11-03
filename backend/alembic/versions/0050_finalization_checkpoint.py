"""Add durable final response rendering checkpoints.

Revision ID: 0050_finalization_checkpoint
Revises: 0049_runtime_diagnostic_traces
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0050_finalization_checkpoint"
down_revision: str | None = "0049_runtime_diagnostic_traces"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_ID = "NULLIF(current_setting('app.current_tenant_id', true), '')"


def upgrade() -> None:
    op.create_table(
        "interaction_finalizations",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("interaction_id", sa.String(length=64), nullable=False),
        sa.Column(
            "phase",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'prepared'"),
        ),
        sa.Column("output_id", sa.String(length=64), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("terminal_status", sa.String(length=32), nullable=False),
        sa.Column(
            "render_messages",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "completion_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "interaction_id"],
            ["interactions.tenant_id", "interactions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("interaction_id", name="uq_interaction_finalization_interaction"),
    )
    op.create_index(
        "ix_interaction_finalization_resume",
        "interaction_finalizations",
        ["tenant_id", "phase"],
        unique=False,
    )
    op.execute("ALTER TABLE interaction_finalizations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE interaction_finalizations FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY interaction_finalizations_tenant_access "
        "ON interaction_finalizations "
        f"FOR ALL USING (tenant_id = {TENANT_ID}) "
        f"WITH CHECK (tenant_id = {TENANT_ID})"
    )
    op.create_index(
        "ix_interaction_finalization_expiry",
        "interaction_finalizations",
        ["tenant_id", "expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.execute("DROP POLICY interaction_finalizations_tenant_access ON interaction_finalizations")
    op.execute("ALTER TABLE interaction_finalizations NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE interaction_finalizations DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_interaction_finalization_expiry", table_name="interaction_finalizations")
    op.drop_index("ix_interaction_finalization_resume", table_name="interaction_finalizations")
    op.drop_table("interaction_finalizations")
