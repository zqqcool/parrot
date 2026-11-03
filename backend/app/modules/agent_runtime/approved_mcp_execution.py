from __future__ import annotations

from app.core.agent_runtime import RuntimeMcpServerProfile
from app.modules.agent_runtime.capability_presentation import capability_failure
from app.modules.agent_runtime.mcp_executor import McpExecutor, RuntimeMcpTool
from app.modules.mcp_servers.tool_policy import arguments_match_schema, policy_for_tool


async def execute_approved_mcp(
    *,
    executor: McpExecutor | None,
    tools: tuple[RuntimeMcpTool, ...],
    servers: tuple[RuntimeMcpServerProfile, ...],
    capability_id: str,
    input_payload: dict[str, object],
    expected_schema_hash: str,
) -> dict[str, object]:
    if executor is None:
        return capability_failure("MCP_EXECUTION_NOT_ENABLED", "MCP execution is not enabled")
    tool = next((item for item in tools if item.capability_id == capability_id), None)
    if tool is None:
        return capability_failure("MCP_CAPABILITY_NOT_FOUND", "Approved capability is unavailable")
    server = next((item for item in servers if item.id == tool.server_id), None)
    policy = policy_for_tool(server, tool) if server is not None else None
    if (
        policy is None
        or policy.approval != "required"
        or policy.schema_hash != expected_schema_hash
        or not arguments_match_schema(input_payload, policy.input_schema)
    ):
        return capability_failure(
            "MCP_APPROVAL_STALE", "Approved action no longer matches its policy"
        )
    return await executor.execute(tool, input_payload)
