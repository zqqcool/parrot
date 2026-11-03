from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.modules.agent_runtime.observations import ToolObservation
from app.modules.agent_runtime.planner import AgentPlan

TerminalCandidateDecisionKind = Literal["deliver", "repair", "partial"]
TerminalCandidateReason = Literal[
    "empty_response",
    "capability_observation_required",
]


@dataclass(frozen=True)
class TerminalCandidateDecision:
    kind: TerminalCandidateDecisionKind
    reason: TerminalCandidateReason | None = None


def terminal_candidate_decision(
    content: str,
    plan: AgentPlan,
    *,
    observations: tuple[ToolObservation, ...],
    repair_attempts: int,
    max_repair_attempts: int,
) -> TerminalCandidateDecision:
    reason = _candidate_block_reason(content, plan, observations)
    if reason is None:
        return TerminalCandidateDecision(kind="deliver")
    if repair_attempts < max_repair_attempts:
        return TerminalCandidateDecision(kind="repair", reason=reason)
    return TerminalCandidateDecision(kind="partial", reason=reason)


def terminal_repair_instruction(reason: TerminalCandidateReason) -> str:
    if reason == "capability_observation_required":
        return (
            "Planner 已明确要求本回合使用运行时能力，但尚未尝试任何工具。请使用当前可用工具"
            "继续处理；如果工具失败，取得失败结果后再如实说明限制。"
        )
    return "刚才没有生成可交付文本。请直接给出完整用户答复，或调用确有必要的工具。"


def partial_message(reason: TerminalCandidateReason) -> str:
    if reason == "capability_observation_required":
        return "暂时未获得完成此请求所需的信息，请稍后重试。"
    return "暂时未能生成有效答复，请稍后重试。"


def can_speculate_terminal_content(
    plan: AgentPlan,
    observations: tuple[ToolObservation, ...],
) -> bool:
    """Whether answer tokens may be public before the stream proves there are no tools.

    Capability plans still waiting for an observation must not flash a draft answer.
    """

    return _candidate_block_reason("pending", plan, observations) is None


def _candidate_block_reason(
    content: str,
    plan: AgentPlan,
    observations: tuple[ToolObservation, ...],
) -> TerminalCandidateReason | None:
    if not content.strip():
        return "empty_response"
    if (
        plan.action == "capability_lookup"
        and not plan.capability_prefetched
        and not any(_satisfies_capability_plan(item, plan) for item in observations)
    ):
        return "capability_observation_required"
    return None


def _satisfies_capability_plan(observation: ToolObservation, plan: AgentPlan) -> bool:
    if plan.capability_query:
        if observation.tool_name == "capability_execute":
            return observation.kind in {"instruction", "read", "action", "failure"}
        return observation.tool_name == "capability_search" and observation.kind == "read"
    return observation.kind in {"instruction", "read", "action", "subagent", "failure"}
