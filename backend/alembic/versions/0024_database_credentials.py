"""Store provider credentials as encrypted database values.

Revision ID: 0024_database_credentials
Revises: 0023_llm_runtime_parameters
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0024_database_credentials"
down_revision: str | None = "0023_llm_runtime_parameters"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("llm_configs", sa.Column("credential_envelope", sa.Text(), nullable=True))
    op.drop_column("llm_configs", "credential_ref")
    op.add_column(
        "mcp_servers",
        sa.Column(
            "encrypted_credentials",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.drop_column("mcp_servers", "secret_refs")


def downgrade() -> None:
    op.add_column(
        "mcp_servers",
        sa.Column(
            "secret_refs",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.drop_column("mcp_servers", "encrypted_credentials")
    op.add_column("llm_configs", sa.Column("credential_ref", sa.String(256), nullable=True))
    op.drop_column("llm_configs", "credential_envelope")
