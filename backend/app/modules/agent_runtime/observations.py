from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.modules.agent_runtime.contracts import ToolCall
from app.modules.agent_runtime.knowledge_output import (
    KnowledgeCitationInventoryItem,
    inventory_from_tool_result,
)

ObservationKind = Literal["control", "instruction", "read", "action", "subagent", "failure"]
_SUCCESS_STATUSES = frozenset({"instruction_ready", "ok", "succeeded"})
_FAILURE_STATUSES = frozenset({"failed", "rejected"})


@dataclass(frozen=True)
class ToolObservation:
    tool_name: str
    call_id: str
    kind: ObservationKind
    succeeded: bool
    result_status: str
    knowledge_citations: tuple[KnowledgeCitationInventoryItem, ...] = ()


def observation_from(call: ToolCall, result: dict[str, object]) -> ToolObservation:
    status = result.get("status")
    result_status = status if isinstance(status, str) else "unknown"
    succeeded = result_status in _SUCCESS_STATUSES
    knowledge_citations = (
        inventory_from_tool_result(result) if call.name == "knowledge_search" else ()
    )
    return ToolObservation(
        tool_name=call.name,
        call_id=call.id,
        kind=_observation_kind(call, result, result_status),
        succeeded=succeeded,
        result_status=result_status,
        knowledge_citations=knowledge_citations,
    )


def _observation_kind(
    call: ToolCall, result: dict[str, object], result_status: str
) -> ObservationKind:
    if call.name == "capability_search":
        capabilities = result.get("capabilities")
        action = call.arguments.get("action")
        if (
            action in {"find", "find_and_load"}
            and result_status == "ok"
            and isinstance(capabilities, list)
            and not capabilities
        ):
            return "read"
        return "control"
    if call.name == "capability_execute":
        if result_status == "instruction_ready":
            return "instruction"
        return "failure" if result_status in _FAILURE_STATUSES else "action"
    if result_status in _FAILURE_STATUSES:
        return "failure"
    if call.name in {"knowledge_search", "memory", "time", "math"}:
        return "read"
    if call.name == "subagent_dispatch":
        return "subagent"
    if call.name in {"schedule", "script", "todo"}:
        return "action"
    return "control"
