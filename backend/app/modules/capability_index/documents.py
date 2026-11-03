from __future__ import annotations


def skill_index_text(name: str, description: str, instructions: str) -> str:
    return f"name: {name}\ndescription: {description}\nSKILL.md:\n{instructions}"


def mcp_tool_index_text(server_name: str, tool_name: str, description: str) -> str:
    return f"server: {server_name}\ntool: {tool_name}\ndescription: {description}"
