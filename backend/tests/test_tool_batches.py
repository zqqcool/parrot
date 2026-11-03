from __future__ import annotations

from app.modules.agent_runtime.contracts import ToolCall
from app.modules.agent_runtime.tool_batches import tool_call_batches


def test_parallel_read_batches_preserve_serial_barriers_and_order() -> None:
    calls = (
        _call("knowledge_a", "knowledge_search"),
        _call("knowledge_b", "knowledge_search"),
        _call("capability", "capability_execute"),
        _call("knowledge_c", "knowledge_search"),
    )

    batches = tool_call_batches(calls, max_parallel_calls=3)

    assert [[call.id for call in batch] for batch in batches] == [
        ["knowledge_a", "knowledge_b"],
        ["capability"],
        ["knowledge_c"],
    ]


def test_policy_approved_capabilities_share_only_their_safe_batch() -> None:
    calls = (
        _capability("mcp:docs:search_a"),
        _capability("mcp:docs:search_b"),
        _capability("mcp:docs:mutate"),
    )

    batches = tool_call_batches(
        calls,
        max_parallel_calls=3,
        is_parallel_safe=lambda call: call.arguments.get("capability_id")
        in {"mcp:docs:search_a", "mcp:docs:search_b"},
    )

    assert [[call.arguments["capability_id"] for call in batch] for batch in batches] == [
        ["mcp:docs:search_a", "mcp:docs:search_b"],
        ["mcp:docs:mutate"],
    ]


def _call(call_id: str, name: str) -> ToolCall:
    return ToolCall(id=call_id, name=name, arguments={})


def _capability(capability_id: str) -> ToolCall:
    return ToolCall(
        id=capability_id,
        name="capability_execute",
        arguments={"capability_id": capability_id, "input": {}},
    )
