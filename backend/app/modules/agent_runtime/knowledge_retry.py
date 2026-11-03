from __future__ import annotations

import json
from typing import cast

from app.modules.agent_runtime.contracts import ChatMessage, ToolCall


def exhausted_no_results_retry(
    messages: list[ChatMessage], call: ToolCall
) -> dict[str, object] | None:
    """Permit one follow-up search after a no-results response."""
    if call.name != "knowledge_search":
        return None
    statuses = tuple(
        status for message in messages if (status := _retrieval_status(message)) is not None
    )
    if statuses[-2:] != ("no_results", "no_results"):
        return None
    return {
        "status": "rejected",
        "code": "KNOWLEDGE_NO_RESULTS_RETRY_EXHAUSTED",
        "message": (
            "A no-results search has already been retried once; answer without claiming evidence."
        ),
    }


def _retrieval_status(message: ChatMessage) -> str | None:
    if message.role != "tool" or message.name != "knowledge_search" or not message.content:
        return None
    try:
        payload = json.loads(message.content)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    value = cast(dict[str, object], payload).get("retrieval_status")
    return value if isinstance(value, str) else None
