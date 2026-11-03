from __future__ import annotations

from app.core.agent_runtime import RuntimeSkillProfile
from app.modules.agent_runtime.mcp_executor import RuntimeMcpTool
from app.modules.capability_index.documents import mcp_tool_index_text, skill_index_text
from app.modules.capability_index.ranking import CapabilitySearchDocument


def skill_view(skill: RuntimeSkillProfile) -> dict[str, object]:
    return {
        "id": skill.id,
        "kind": "skill",
        "name": skill.name,
        "description": skill.description,
        "version": skill.version,
    }


def mcp_tool_view(tool: RuntimeMcpTool) -> dict[str, object]:
    return {
        "id": tool.capability_id,
        "kind": "mcp",
        "name": tool.tool_name,
        "server_name": tool.server_name,
        "description": tool.description,
        "input_schema": tool.input_schema,
        "read_only": tool.read_only,
    }


def skill_index_document(skill: RuntimeSkillProfile) -> str:
    return skill_index_text(skill.name, skill.description, skill.instructions)


def mcp_index_document(tool: RuntimeMcpTool) -> str:
    return mcp_tool_index_text(tool.server_name, tool.tool_name, tool.description)


def lexical_ranking(query: str, documents: tuple[CapabilitySearchDocument, ...]) -> tuple[str, ...]:
    normalized = query.casefold().strip()
    if not normalized:
        return tuple(item.source_id for item in documents)
    return tuple(item.source_id for item in documents if normalized in item.text.casefold())


def bounded_instructions(value: str) -> str:
    return value[:12_000]


def capability_failure(code: str, message: str) -> dict[str, object]:
    return {"status": "rejected", "code": code, "message": message}
