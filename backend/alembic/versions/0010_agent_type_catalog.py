"""Add system-owned agent interaction type catalog.

Revision ID: 0010_agent_type_catalog
Revises: 0009_agent_avatar_storage
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010_agent_type_catalog"
down_revision: str | None = "0009_agent_avatar_storage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_AGENT_TYPES = [
    {
        "key": "functional",
        "name": "功能型",
        "description": "面向复杂任务的自主推理，可使用本地沙盒执行环境。",
    },
    {
        "key": "knowledge",
        "name": "知识型",
        "description": "优先检索、理解和整合知识内容，不提供本地执行环境。",
    },
    {
        "key": "voice",
        "name": "语音型",
        "description": "针对自然语音交互优化，不提供本地执行环境。",
    },
]


def upgrade() -> None:
    op.create_table(
        "agent_types",
        sa.Column("key", sa.String(length=32), primary_key=True),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
    )
    op.bulk_insert(
        sa.table("agent_types", *[sa.column(key) for key in _AGENT_TYPES[0]]), _AGENT_TYPES
    )
    op.add_column(
        "agent_publications",
        sa.Column(
            "agent_type_key",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'knowledge'"),
        ),
    )
    op.create_foreign_key(
        "fk_agent_publication_type",
        "agent_publications",
        "agent_types",
        ["agent_type_key"],
        ["key"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint("fk_agent_publication_type", "agent_publications", type_="foreignkey")
    op.drop_column("agent_publications", "agent_type_key")
    op.drop_table("agent_types")
