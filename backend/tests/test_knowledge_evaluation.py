from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from app.modules.knowledge.evaluation import (
    KnowledgeEvaluationCase,
    evaluate_retrieval,
    load_evaluation_cases,
)
from app.modules.knowledge.runtime import KnowledgeEvidenceBundle, KnowledgeRuntimePort


class EvaluationRuntime:
    def __init__(self, results: tuple[KnowledgeEvidenceBundle, ...]) -> None:
        self._results = iter(results)

    async def retrieve(self, _context: object) -> KnowledgeEvidenceBundle:
        return next(self._results)


def test_evaluation_dataset_is_strict_and_requires_unique_case_ids(tmp_path: Path) -> None:
    dataset = tmp_path / "knowledge-eval.jsonl"
    dataset.write_text(
        "\n".join(
            (
                '{"case_id":"release","query":"policy","expected_citation_ids":["a"]}',
                '{"case_id":"release","query":"rollback","expected_citation_ids":["b"]}',
            )
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="case_id"):
        load_evaluation_cases(dataset)


@pytest.mark.asyncio
async def test_evaluation_reports_recall_mrr_and_fallback_rate() -> None:
    cases = (
        KnowledgeEvaluationCase(
            case_id="release",
            query="release policy",
            expected_citation_ids=("a", "b"),
            limit=3,
        ),
        KnowledgeEvaluationCase(
            case_id="rollback",
            query="rollback policy",
            expected_citation_ids=("c",),
            limit=3,
        ),
    )
    runtime = EvaluationRuntime(
        (
            KnowledgeEvidenceBundle(
                citation_ids=("x", "a"), status="ok", retrieval_method="hybrid"
            ),
            KnowledgeEvidenceBundle(
                citation_ids=(), status="no_results", retrieval_method="lexical_fallback"
            ),
        )
    )

    result = await evaluate_retrieval(
        cast(KnowledgeRuntimePort, runtime), "tenant_test", "agent_test", cases
    )

    assert result.total_cases == 2
    assert result.recall_at_k == 0.25
    assert result.mean_reciprocal_rank == 0.25
    assert result.empty_result_rate == 0.5
    assert result.unavailable_rate == 0
    assert result.hybrid_cases == 1
    assert result.lexical_fallback_cases == 1
