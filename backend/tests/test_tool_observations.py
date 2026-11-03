from __future__ import annotations

from app.modules.agent_runtime.contracts import ToolCall
from app.modules.agent_runtime.observations import observation_from


def test_instruction_result_is_not_classified_as_an_action_receipt() -> None:
    observation = observation_from(
        ToolCall(
            id="call_skill",
            name="capability_execute",
            arguments={"capability_id": "skill_test"},
        ),
        {"status": "instruction_ready", "instructions": "Collect the city."},
    )

    assert observation.kind == "instruction"
    assert observation.succeeded is True


def test_empty_capability_search_is_a_deterministic_negative_read() -> None:
    observation = observation_from(
        ToolCall(
            id="call_find",
            name="capability_search",
            arguments={"action": "find", "query": "release notes"},
        ),
        {"status": "ok", "capabilities": []},
    )

    assert observation.kind == "read"
    assert observation.succeeded is True


def test_empty_find_and_load_is_also_a_negative_read() -> None:
    observation = observation_from(
        ToolCall(
            id="call_find_and_load",
            name="capability_search",
            arguments={"action": "find_and_load", "query": "release notes"},
        ),
        {"status": "ok", "capabilities": []},
    )

    assert observation.kind == "read"
    assert observation.succeeded is True


def test_ranked_capability_candidates_remain_a_control_plane_observation() -> None:
    observation = observation_from(
        ToolCall(
            id="call_find",
            name="capability_search",
            arguments={"action": "find", "query": "release notes"},
        ),
        {"status": "ok", "capabilities": [{"id": "skill_test"}]},
    )

    assert observation.kind == "control"


def test_successful_find_and_load_remains_control_until_execute() -> None:
    observation = observation_from(
        ToolCall(
            id="call_find_and_load",
            name="capability_search",
            arguments={"action": "find_and_load", "query": "release notes"},
        ),
        {
            "status": "ok",
            "capabilities": [{"id": "skill_test", "kind": "skill"}],
            "instructions": "Do the thing.",
        },
    )

    assert observation.kind == "control"
