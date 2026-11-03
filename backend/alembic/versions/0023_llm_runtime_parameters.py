"""Add per-LLM runtime generation parameters.

Revision ID: 0023_llm_runtime_parameters
Revises: 0022_conversation_messages
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0023_llm_runtime_parameters"
down_revision: str | None = "0022_conversation_messages"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "llm_configs",
        sa.Column("temperature", sa.Float(), nullable=False, server_default="0.2"),
    )
    op.add_column(
        "llm_configs",
        sa.Column("max_tokens", sa.Integer(), nullable=False, server_default="4096"),
    )
    op.add_column(
        "llm_configs",
        sa.Column("thinking_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("llm_configs", "thinking_enabled")
    op.drop_column("llm_configs", "max_tokens")
    op.drop_column("llm_configs", "temperature")
