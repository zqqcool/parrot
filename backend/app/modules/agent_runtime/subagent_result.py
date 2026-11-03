from __future__ import annotations

import json
from typing import cast

from app.modules.mcp_servers.tool_policy import arguments_match_schema

_MAX_RESULT_CONTENT = 16_000


def normalize_child_result(
    interaction_status: str,
    event_data: dict[str, object],
    result_schema: dict[str, object],
) -> tuple[str, dict[str, object]]:
    status = _task_status(interaction_status)
    content = event_data.get("content")
    result: dict[str, object] = {
        "content": content[:_MAX_RESULT_CONTENT] if isinstance(content, str) else None,
        "code": event_data.get("code"),
    }
    if status != "completed" or not result_schema:
        return status, result
    structured = _structured_output(content)
    if structured is None or not arguments_match_schema(structured, result_schema):
        return "failed", {
            **result,
            "code": "SUBAGENT_RESULT_SCHEMA_INVALID",
        }
    result["structured_output"] = structured
    return status, result


def _structured_output(content: object) -> dict[str, object] | None:
    if not isinstance(content, str):
        return None
    try:
        value = json.loads(content)
    except json.JSONDecodeError:
        return None
    return cast(dict[str, object], value) if isinstance(value, dict) else None


def _task_status(interaction_status: str) -> str:
    return interaction_status if interaction_status in {"completed", "cancelled"} else "failed"
