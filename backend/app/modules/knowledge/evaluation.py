from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from pydantic import BaseModel, ConfigDict, Field

from app.modules.knowledge.runtime import KnowledgeRuntimeContext, KnowledgeRuntimePort


class KnowledgeEvaluationCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1, max_length=191)
    query: str = Field(min_length=1, max_length=1_000)
    expected_citation_ids: tuple[str, ...] = Field(min_length=1, max_length=100)
    limit: int = Field(default=6, ge=1, le=12)


@dataclass(frozen=True)
class KnowledgeEvaluationReport:
    total_cases: int
    recall_at_k: float
    mean_reciprocal_rank: float
    empty_result_rate: float
    unavailable_rate: float
    lexical_cases: int
    hybrid_cases: int
    lexical_fallback_cases: int


def load_evaluation_cases(path: Path) -> tuple[KnowledgeEvaluationCase, ...]:
    cases: list[KnowledgeEvaluationCase] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            value = cast(object, json.loads(line))
            cases.append(KnowledgeEvaluationCase.model_validate(value))
        except (json.JSONDecodeError, ValueError) as error:
            raise ValueError(f"Invalid knowledge evaluation case at line {line_number}") from error
    if not cases:
        raise ValueError("Knowledge evaluation dataset is empty")
    if len({item.case_id for item in cases}) != len(cases):
        raise ValueError("Knowledge evaluation case_id values must be unique")
    return tuple(cases)


async def evaluate_retrieval(
    runtime: KnowledgeRuntimePort,
    tenant_id: str,
    agent_id: str,
    cases: tuple[KnowledgeEvaluationCase, ...],
) -> KnowledgeEvaluationReport:
    recall_total = 0.0
    reciprocal_rank_total = 0.0
    empty_count = 0
    unavailable_count = 0
    methods = {"lexical": 0, "hybrid": 0, "lexical_fallback": 0}
    for case in cases:
        result = await runtime.retrieve(
            KnowledgeRuntimeContext(
                tenant_id=tenant_id,
                agent_id=agent_id,
                query=case.query,
                limit=case.limit,
            )
        )
        expected = set(case.expected_citation_ids)
        retrieved = result.citation_ids
        recall_total += len(expected.intersection(retrieved)) / len(expected)
        reciprocal_rank_total += _reciprocal_rank(retrieved, expected)
        empty_count += not retrieved
        unavailable_count += result.status == "unavailable"
        if result.retrieval_method in methods:
            methods[result.retrieval_method] += 1
    total = len(cases)
    return KnowledgeEvaluationReport(
        total_cases=total,
        recall_at_k=recall_total / total,
        mean_reciprocal_rank=reciprocal_rank_total / total,
        empty_result_rate=empty_count / total,
        unavailable_rate=unavailable_count / total,
        lexical_cases=methods["lexical"],
        hybrid_cases=methods["hybrid"],
        lexical_fallback_cases=methods["lexical_fallback"],
    )


def _reciprocal_rank(retrieved: tuple[str, ...], expected: set[str]) -> float:
    for rank, citation_id in enumerate(retrieved, start=1):
        if citation_id in expected:
            return 1.0 / rank
    return 0.0
