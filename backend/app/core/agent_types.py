from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class AgentTypeKey(StrEnum):
    FUNCTIONAL = "functional"
    KNOWLEDGE = "knowledge"
    VOICE = "voice"


@dataclass(frozen=True)
class AgentTypePolicy:
    key: AgentTypeKey
    uses_knowledge: bool
    restricts_executable_skills: bool
    allows_runtime_tools: bool
    uses_functional_planner: bool


_POLICIES = {
    AgentTypeKey.FUNCTIONAL: AgentTypePolicy(
        key=AgentTypeKey.FUNCTIONAL,
        uses_knowledge=False,
        restricts_executable_skills=False,
        allows_runtime_tools=True,
        uses_functional_planner=True,
    ),
    AgentTypeKey.KNOWLEDGE: AgentTypePolicy(
        key=AgentTypeKey.KNOWLEDGE,
        uses_knowledge=True,
        restricts_executable_skills=True,
        allows_runtime_tools=True,
        uses_functional_planner=False,
    ),
    AgentTypeKey.VOICE: AgentTypePolicy(
        key=AgentTypeKey.VOICE,
        uses_knowledge=False,
        restricts_executable_skills=False,
        allows_runtime_tools=False,
        uses_functional_planner=False,
    ),
}


def agent_type_policy(key: str) -> AgentTypePolicy | None:
    try:
        return _POLICIES[AgentTypeKey(key)]
    except (KeyError, ValueError):
        return None
