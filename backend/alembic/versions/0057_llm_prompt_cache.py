"""Add administrator-declared prompt cache intent.

Revision ID: 0057_llm_prompt_cache
Revises: 0056_agent_capability_threshold
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0057_llm_prompt_cache"
down_revision: str | None = "0056_agent_capability_threshold"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "llm_configs",
        sa.Column(
            "prompt_cache_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("llm_configs", "prompt_cache_enabled")
