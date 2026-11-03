from __future__ import annotations

import hashlib
import json

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError

from app.core.agent_runtime import RuntimeMcpServerProfile, RuntimeMcpToolPolicy
from app.modules.agent_runtime.mcp_executor import RuntimeMcpTool


def mcp_schema_hash(schema: dict[str, object]) -> str:
    canonical = json.dumps(
        schema, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


def automatic_read_policy(
    server: RuntimeMcpServerProfile, tool: RuntimeMcpTool
) -> RuntimeMcpToolPolicy | None:
    policy = next((item for item in server.tool_policies if item.name == tool.tool_name), None)
    if (
        policy is None
        or policy.effect != "read"
        or policy.approval != "automatic"
        or policy.schema_hash != mcp_schema_hash(tool.input_schema)
    ):
        return None
    return policy


def parallel_safe_policy(
    server: RuntimeMcpServerProfile, tool: RuntimeMcpTool
) -> RuntimeMcpToolPolicy | None:
    policy = automatic_read_policy(server, tool)
    return policy if policy is not None and policy.parallel_safe else None


def policy_for_tool(
    server: RuntimeMcpServerProfile, tool: RuntimeMcpTool
) -> RuntimeMcpToolPolicy | None:
    policy = next((item for item in server.tool_policies if item.name == tool.tool_name), None)
    if policy is None or policy.schema_hash != mcp_schema_hash(tool.input_schema):
        return None
    return policy


def enabled_tool_policy(
    server: RuntimeMcpServerProfile, tool: RuntimeMcpTool
) -> RuntimeMcpToolPolicy | None:
    policy = policy_for_tool(server, tool)
    if policy is None or (policy.effect, policy.approval) not in {
        ("read", "automatic"),
        ("read", "required"),
        ("side_effect", "required"),
    }:
        return None
    return policy


def arguments_match_schema(arguments: dict[str, object], schema: dict[str, object]) -> bool:
    try:
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(arguments)  # pyright: ignore[reportUnknownMemberType]
    except (SchemaError, ValidationError):
        return False
    return True
