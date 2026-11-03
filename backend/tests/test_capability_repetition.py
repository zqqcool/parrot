from __future__ import annotations

from app.modules.agent_runtime.capability_repetition import repeated_capability_execute


def test_repetition_uses_the_current_capability_id_contract() -> None:
    history = [{"capability_id": "mcp:docs:search", "input": {"query": "release notes"}}]

    repeated = repeated_capability_execute(
        history,
        {"capability_id": "mcp:docs:search", "input": {"query": "release notes"}},
        exact_limit=1,
        similar_limit=2,
        similarity_threshold=0.6,
    )
    different = repeated_capability_execute(
        history,
        {"capability_id": "mcp:issues:search", "input": {"query": "release notes"}},
        exact_limit=1,
        similar_limit=2,
        similarity_threshold=0.6,
    )

    assert repeated == "exact_repeat"
    assert different is None
