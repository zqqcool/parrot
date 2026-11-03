from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.knowledge.merge_policy import (
    MERGE_MIN_RERANK_SCORE_MAX,
    MERGE_MIN_RERANK_SCORE_MIN,
    MERGE_MINIMUM_SPACE_HITS,
    MERGE_PER_SPACE_CANDIDATE_CAP,
    MERGE_RERANK_TOP_N_DEFAULT,
    MERGE_RERANK_TOP_N_MAX,
    MERGE_RERANK_TOP_N_MIN,
    MERGE_RESULT_TOP_K_DEFAULT,
    MERGE_RESULT_TOP_K_MAX,
    MERGE_RESULT_TOP_K_MIN,
)


class KnowledgeMergeSettingsUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    merge_rerank_enabled: bool = False
    reranker_config_id: str | None = Field(default=None, max_length=64)
    rerank_top_n: int = Field(
        default=MERGE_RERANK_TOP_N_DEFAULT,
        ge=MERGE_RERANK_TOP_N_MIN,
        le=MERGE_RERANK_TOP_N_MAX,
    )
    result_top_k: int = Field(
        default=MERGE_RESULT_TOP_K_DEFAULT,
        ge=MERGE_RESULT_TOP_K_MIN,
        le=MERGE_RESULT_TOP_K_MAX,
    )
    min_rerank_score: float | None = Field(
        default=None,
        ge=MERGE_MIN_RERANK_SCORE_MIN,
        le=MERGE_MIN_RERANK_SCORE_MAX,
    )

    @model_validator(mode="after")
    def validate_dependencies(self) -> KnowledgeMergeSettingsUpdateRequest:
        if self.merge_rerank_enabled and self.reranker_config_id is None:
            raise ValueError("merge reranking requires a reranker_config_id")
        if not self.merge_rerank_enabled and self.reranker_config_id is not None:
            raise ValueError("reranker_config_id requires merge_rerank_enabled")
        if not self.merge_rerank_enabled and self.min_rerank_score is not None:
            raise ValueError("min_rerank_score requires merge_rerank_enabled")
        if self.rerank_top_n < self.result_top_k:
            raise ValueError("rerank_top_n must be greater than or equal to result_top_k")
        return self


class KnowledgeMergePolicyView(BaseModel):
    minimum_space_hits: int = MERGE_MINIMUM_SPACE_HITS
    per_space_candidate_cap: int = MERGE_PER_SPACE_CANDIDATE_CAP
    rerank_top_n_min: int = MERGE_RERANK_TOP_N_MIN
    rerank_top_n_max: int = MERGE_RERANK_TOP_N_MAX
    result_top_k_min: int = MERGE_RESULT_TOP_K_MIN
    result_top_k_max: int = MERGE_RESULT_TOP_K_MAX
    min_rerank_score_min: float = MERGE_MIN_RERANK_SCORE_MIN
    min_rerank_score_max: float = MERGE_MIN_RERANK_SCORE_MAX


class KnowledgeMergeSettingsView(BaseModel):
    tenant_id: str
    merge_rerank_enabled: bool
    reranker_config_id: str | None
    rerank_top_n: int
    result_top_k: int
    min_rerank_score: float | None
    policy: KnowledgeMergePolicyView
    updated_at: datetime | None = None
