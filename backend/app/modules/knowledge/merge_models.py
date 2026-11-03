from __future__ import annotations

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base, TimestampMixin
from app.modules.knowledge.merge_policy import (
    MERGE_RERANK_TOP_N_DEFAULT,
    MERGE_RESULT_TOP_K_DEFAULT,
)


class KnowledgeMergeSettings(Base, TimestampMixin):
    """Tenant-scoped multi-space merge policy for agent knowledge retrieval."""

    __tablename__ = "knowledge_merge_settings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "reranker_config_id"],
            ["reranker_configs.tenant_id", "reranker_configs.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "rerank_top_n BETWEEN 1 AND 60",
            name="ck_knowledge_merge_settings_rerank_top_n",
        ),
        CheckConstraint(
            "result_top_k BETWEEN 1 AND 12",
            name="ck_knowledge_merge_settings_result_top_k",
        ),
        CheckConstraint(
            "rerank_top_n >= result_top_k",
            name="ck_knowledge_merge_settings_top_n_gte_top_k",
        ),
        CheckConstraint(
            "min_rerank_score IS NULL OR min_rerank_score BETWEEN 0 AND 1",
            name="ck_knowledge_merge_settings_min_score",
        ),
        CheckConstraint(
            "(merge_rerank_enabled AND reranker_config_id IS NOT NULL) OR "
            "(NOT merge_rerank_enabled AND reranker_config_id IS NULL)",
            name="ck_knowledge_merge_settings_reranker_dependency",
        ),
        CheckConstraint(
            "merge_rerank_enabled OR min_rerank_score IS NULL",
            name="ck_knowledge_merge_settings_score_dependency",
        ),
    )

    tenant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True
    )
    merge_rerank_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reranker_config_id: Mapped[str | None] = mapped_column(String(64))
    rerank_top_n: Mapped[int] = mapped_column(
        Integer, default=MERGE_RERANK_TOP_N_DEFAULT, nullable=False
    )
    result_top_k: Mapped[int] = mapped_column(
        Integer, default=MERGE_RESULT_TOP_K_DEFAULT, nullable=False
    )
    min_rerank_score: Mapped[float | None] = mapped_column(Float)
