from __future__ import annotations

from app.modules.agent_runtime.contracts import ToolCall

_CONTROL_PLANE_ERROR_CODES = frozenset(
    {
        "TOOL_NOT_AVAILABLE",
        "CAPABILITY_NOT_FOUND",
        "MCP_CAPABILITY_NOT_FOUND",
        "MCP_EXECUTION_FAILED",
    }
)


def control_plane_error_code(call: ToolCall, result: dict[str, object]) -> str | None:
    """Return a routing failure that merits one bounded orchestration retry."""

    if not call.name or result.get("status") not in {"failed", "rejected"}:
        return None
    code = result.get("code")
    return code if isinstance(code, str) and code in _CONTROL_PLANE_ERROR_CODES else None
