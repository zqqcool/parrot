"""Merge concurrent agent-type and Skill-package migration heads.

Revision ID: 0011_agent_skill_merge
Revises: 0010_agent_type_catalog, 0010_skill_package_metadata
"""

from collections.abc import Sequence

revision: str = "0011_agent_skill_merge"
down_revision: tuple[str, str] = (
    "0010_agent_type_catalog",
    "0010_skill_package_metadata",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
