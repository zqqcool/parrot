from __future__ import annotations

from dataclasses import replace
from typing import cast

from app.core.agent_runtime import (
    AgentRuntimeProfile,
    RuntimeMcpServerProfile,
    RuntimeMcpToolPolicy,
    RuntimeSkillProfile,
)
from app.modules.agent_runtime.taskboard import TaskBoardTask
from app.modules.interactions.runtime import RuntimeActiveSkill, RuntimeSkillContext


def derive_child_profile(
    parent: AgentRuntimeProfile,
    task: TaskBoardTask,
    *,
    source: str,
) -> AgentRuntimeProfile:
    """Derive a least-privilege child profile for loop-origin delegation."""

    scope = task.capability_scope if source == "agent_loop" else _legacy_read_scope(parent)
    skills = _scoped_skills(parent, scope)
    servers = _scoped_mcp_servers(parent, scope)
    knowledge_enabled = scope.get("knowledge_enabled", parent.is_knowledge_only)
    if not isinstance(knowledge_enabled, bool):
        raise ValueError("subagent capability scope is invalid")
    if knowledge_enabled and not parent.is_knowledge_only:
        raise ValueError("subagent scope must be a read-only subset of the parent")
    return replace(
        parent,
        skills=skills,
        mcp_servers=servers,
        agent_type_key="knowledge" if knowledge_enabled else "functional",
    )


def derive_child_skill_context(
    profile: AgentRuntimeProfile,
    task: TaskBoardTask,
    *,
    source: str,
) -> RuntimeSkillContext:
    if source != "agent_loop":
        return RuntimeSkillContext(supporting=tuple(_active(skill) for skill in profile.skills))
    primary_value = task.capability_scope.get("primary_skill")
    primary = _active_reference(profile, primary_value) if primary_value is not None else None
    supporting_value = task.capability_scope.get("supporting_skills", [])
    if not isinstance(supporting_value, list):
        raise ValueError("subagent capability scope is invalid")
    supporting = tuple(
        _active_reference(profile, item) for item in cast(list[object], supporting_value)
    )
    return RuntimeSkillContext(primary=primary, supporting=supporting)


def _scoped_skills(
    parent: AgentRuntimeProfile, scope: dict[str, object]
) -> tuple[RuntimeSkillProfile, ...]:
    references: list[tuple[str, int]] = []
    primary = scope.get("primary_skill")
    if primary is not None:
        references.append(_skill_reference(primary))
    supporting = scope.get("supporting_skills", [])
    if not isinstance(supporting, list):
        raise ValueError("subagent capability scope is invalid")
    references.extend(_skill_reference(item) for item in cast(list[object], supporting))
    selected: list[RuntimeSkillProfile] = []
    for skill_id, version in references:
        skill = next(
            (item for item in parent.skills if item.id == skill_id and item.version == version),
            None,
        )
        if skill is None or not skill.is_instruction_only:
            raise ValueError("subagent scope must be a read-only subset of the parent")
        if skill not in selected:
            selected.append(skill)
    return tuple(selected)


def _skill_reference(value: object) -> tuple[str, int]:
    if not isinstance(value, dict):
        raise ValueError("subagent capability scope is invalid")
    raw = cast(dict[str, object], value)
    skill_id, version = raw.get("skill_id"), raw.get("skill_version")
    if not isinstance(skill_id, str) or not skill_id or not isinstance(version, int):
        raise ValueError("subagent capability scope is invalid")
    return skill_id, version


def _active_reference(profile: AgentRuntimeProfile, value: object) -> RuntimeActiveSkill:
    skill_id, version = _skill_reference(value)
    skill = next(
        (item for item in profile.skills if item.id == skill_id and item.version == version), None
    )
    if skill is None:
        raise ValueError("subagent scope must be a read-only subset of the parent")
    return _active(skill)


def _active(skill: RuntimeSkillProfile) -> RuntimeActiveSkill:
    return RuntimeActiveSkill(skill_id=skill.id, skill_version=skill.version)


def _scoped_mcp_servers(
    parent: AgentRuntimeProfile, scope: dict[str, object]
) -> tuple[RuntimeMcpServerProfile, ...]:
    raw_ids = scope.get("mcp_capability_ids", [])
    if not isinstance(raw_ids, list):
        raise ValueError("subagent capability scope is invalid")
    values = cast(list[object], raw_ids)
    if not all(isinstance(item, str) for item in values):
        raise ValueError("subagent capability scope is invalid")
    requested = {cast(str, item) for item in values}
    selected_servers: list[RuntimeMcpServerProfile] = []
    matched: set[str] = set()
    for server in parent.mcp_servers:
        policies = tuple(
            policy
            for policy in server.tool_policies
            if _capability_id(server, policy) in requested and _read_only(policy)
        )
        matched.update(_capability_id(server, policy) for policy in policies)
        if policies:
            selected_servers.append(replace(server, tool_policies=policies))
    if matched != requested:
        raise ValueError("subagent scope must be a read-only subset of the parent")
    return tuple(selected_servers)


def _capability_id(server: RuntimeMcpServerProfile, policy: RuntimeMcpToolPolicy) -> str:
    return f"mcp:{server.id}:{policy.name}"


def _read_only(policy: RuntimeMcpToolPolicy) -> bool:
    return policy.effect == "read" and policy.approval == "automatic"


def _legacy_read_scope(parent: AgentRuntimeProfile) -> dict[str, object]:
    return {
        "supporting_skills": [
            {"skill_id": skill.id, "skill_version": skill.version}
            for skill in parent.skills
            if skill.is_instruction_only
        ],
        "mcp_capability_ids": [
            _capability_id(server, policy)
            for server in parent.mcp_servers
            for policy in server.tool_policies
            if _read_only(policy)
        ],
        "knowledge_enabled": parent.is_knowledge_only,
    }
