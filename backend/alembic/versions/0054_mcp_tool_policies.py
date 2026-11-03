"""Add server-owned MCP tool policy snapshots.

Revision ID: 0054_mcp_tool_policies
Revises: 0053_remove_capability_state
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0054_mcp_tool_policies"
down_revision: str | None = "0053_remove_capability_state"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "mcp_servers",
        sa.Column(
            "tool_policies",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.alter_column("mcp_servers", "tool_policies", server_default=None)


def downgrade() -> None:
    op.drop_column("mcp_servers", "tool_policies")
