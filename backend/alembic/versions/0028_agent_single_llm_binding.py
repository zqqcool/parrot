"""Enforce one LLM configuration per Agent.

Revision ID: 0028_agent_single_llm_binding
Revises: 0027_remove_subagent_bindings
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0028_agent_single_llm_binding"
down_revision: str | None = "0027_remove_subagent_bindings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM agent_llm_config_bindings AS binding "
            "USING ("
            "  SELECT agent_id, tenant_id, llm_config_id, "
            "    row_number() OVER ("
            "      PARTITION BY tenant_id, agent_id "
            "      ORDER BY is_default DESC, llm_config_id ASC"
            "    ) AS row_number "
            "  FROM agent_llm_config_bindings"
            ") AS ranked "
            "WHERE binding.tenant_id = ranked.tenant_id "
            "  AND binding.agent_id = ranked.agent_id "
            "  AND binding.llm_config_id = ranked.llm_config_id "
            "  AND ranked.row_number > 1"
        )
    )
    op.execute(sa.text("UPDATE agent_llm_config_bindings SET is_default = true"))
    op.create_unique_constraint(
        "uq_agent_llm_binding_tenant_agent",
        "agent_llm_config_bindings",
        ["tenant_id", "agent_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_agent_llm_binding_tenant_agent",
        "agent_llm_config_bindings",
        type_="unique",
    )
