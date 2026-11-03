"""Protect Agent bindings when a Skill is deleted.

Revision ID: 0042_skill_delete_restrict
Revises: 0041_skill_artifacts
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0042_skill_delete_restrict"
down_revision: str | Sequence[str] | None = "0041_skill_artifacts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.drop_constraint(
        "agent_skill_bindings_skill_id_tenant_id_fkey",
        "agent_skill_bindings",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_agent_skill_binding_skill_restrict",
        "agent_skill_bindings",
        "skills",
        ["skill_id", "tenant_id"],
        ["id", "tenant_id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint("fk_agent_skill_binding_skill_restrict", "agent_skill_bindings")
    op.create_foreign_key(
        "agent_skill_bindings_skill_id_tenant_id_fkey",
        "agent_skill_bindings",
        "skills",
        ["skill_id", "tenant_id"],
        ["id", "tenant_id"],
        ondelete="CASCADE",
    )
