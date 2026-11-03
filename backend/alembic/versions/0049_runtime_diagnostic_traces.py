"""Persist redacted management-only runtime diagnostic traces.

Revision ID: 0049_runtime_diagnostic_traces
Revises: 0048_remove_message_index_outbox
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0049_runtime_diagnostic_traces"
down_revision: str | None = "0048_remove_message_index_outbox"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None

TENANT_ID = "NULLIF(current_setting('app.current_tenant_id', true), '')"


def upgrade() -> None:
    op.create_table(
        "interaction_diagnostic_traces",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("interaction_id", sa.String(length=64), nullable=False),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
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
        sa.UniqueConstraint("interaction_id", "sequence", name="uq_diagnostic_trace_sequence"),
    )
    op.create_index(
        "ix_diagnostic_trace_interaction",
        "interaction_diagnostic_traces",
        ["tenant_id", "interaction_id", "sequence"],
    )
    op.create_index(
        "ix_diagnostic_trace_expiry",
        "interaction_diagnostic_traces",
        ["tenant_id", "expires_at"],
    )
    op.execute("ALTER TABLE interaction_diagnostic_traces ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE interaction_diagnostic_traces FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY interaction_diagnostic_traces_tenant_access "
        "ON interaction_diagnostic_traces "
        f"FOR ALL USING (tenant_id = {TENANT_ID}) "
        f"WITH CHECK (tenant_id = {TENANT_ID})"
    )


def downgrade() -> None:
    op.execute(
        "DROP POLICY interaction_diagnostic_traces_tenant_access ON interaction_diagnostic_traces"
    )
    op.execute("ALTER TABLE interaction_diagnostic_traces NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE interaction_diagnostic_traces DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_diagnostic_trace_expiry", table_name="interaction_diagnostic_traces")
    op.drop_index("ix_diagnostic_trace_interaction", table_name="interaction_diagnostic_traces")
    op.drop_table("interaction_diagnostic_traces")
