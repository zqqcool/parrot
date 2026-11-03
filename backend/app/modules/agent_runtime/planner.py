from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast

from app.core.agent_runtime import AgentRuntimeProfile
from app.modules.agent_runtime.contracts import AgentModelPort, ChatMessage
from app.modules.agent_runtime.diagnostics import RuntimeDiagnostics
from app.modules.agent_runtime.model_retry import complete_with_retry
from app.modules.agent_runtime.structured_output import (
    StructuredOutputError,
    decode_json_object,
)
from app.modules.agent_runtime.taskboard import create_task_board

PlanAction = Literal["direct_answer", "agent_loop", "capability_lookup", "subagent_dispatch"]


@dataclass(frozen=True)
class AgentPlan:
    action: PlanAction
    capability_query: str | None = None
    tasks: tuple[dict[str, object], ...] = ()
    synthetic: bool = False
    capability_prefetched: bool = False


class AgentPlanProtocolError(ValueError):
    """The planner response cannot be applied without guessing a control-plane action."""


class AgentPlanner:
    """Produces a bounded orchestration decision before the tool loop starts."""

    def __init__(self, model: AgentModelPort, max_model_retries: int = 0) -> None:
        self._model = model
        self._max_model_retries = max_model_retries

    async def plan(
        self,
        profile: AgentRuntimeProfile,
        user_text: str,
        diagnostics: RuntimeDiagnostics | None = None,
    ) -> AgentPlan:
        if not profile.uses_functional_planner:
            return AgentPlan(action="direct_answer")
        completion = await complete_with_retry(
            self._model,
            profile.llm,
            (ChatMessage(role="system", content=_prompt(profile, user_text)),),
            (),
            max_retries=self._max_model_retries,
            diagnostics=diagnostics,
            diagnostic_phase="planner",
        )
        return _parse_plan(completion.content, profile, user_text)


def _prompt(profile: AgentRuntimeProfile, user_text: str) -> str:
    agent_instructions = (
        f"\n\nAgent 专属指令：\n{profile.system_prompt.strip()}"
        if profile.system_prompt.strip()
        else ""
    )
    return (
        "请为当前 Parrot Agent 回合仅选择一个受限的编排动作。仅返回 JSON。"
        "action 只能是 direct_answer、agent_loop、capability_lookup 或 subagent_dispatch。"
        "direct_answer 只用于无需任何工具或补充信息即可完成的回答。agent_loop 用于不需要外部"
        "能力、但仍需继续推理或判断是否缺少必要信息的请求。只要需要 time、memory、schedule、"
        "Skill、MCP 或其他运行时工具，就必须选择 capability_lookup；仅当需要检索已绑定 Skill "
        "或 MCP 时才提供 capability_query，使用内置工具时不要填写 capability_query。"
        "规划阶段不得向用户提问或请求澄清；缺少的信息交给后续 Agent Loop 根据入口能力处理。"
        "capability_lookup 可以提供描述能力的 capability_query，但不得复制用户请求。"
        "subagent_dispatch 必须提供二到五个任务，每个任务都必须引用最新请求中的精确 "
        "source_quote/source_span。运行时会使用此 Agent 已持久化的配置创建子交互。\n\n"
        f"已绑定能力：\n{_capability_summary(profile)}\n\n"
        f"{agent_instructions}\n\n"
        f"用户最新请求：\n{user_text}"
    )


def _capability_summary(profile: AgentRuntimeProfile) -> str:
    skill_lines = [f"- Skill {item.name}：{item.description}" for item in profile.skills]
    mcp_lines = [f"- MCP 服务 {item.name}：可发现其可用工具" for item in profile.mcp_servers]
    return "\n".join((*skill_lines, *mcp_lines)) or "- 无外部能力"


def _parse_plan(value: str | None, profile: AgentRuntimeProfile, user_text: str) -> AgentPlan:
    if not value:
        raise AgentPlanProtocolError("Planner response must contain valid JSON")
    try:
        raw = decode_json_object(value)
    except StructuredOutputError as error:
        raise AgentPlanProtocolError("Planner response must contain valid JSON") from error
    action = raw.get("action")
    if action == "direct_answer":
        return _direct()
    if action == "clarify":
        # Providers may replay an older planner contract. Keep the run moving,
        # but delegate the actual user-input decision to the Agent Loop.
        return AgentPlan(action="agent_loop", synthetic=True)
    if action == "agent_loop":
        return AgentPlan(action="agent_loop")
    if action == "capability_lookup":
        return AgentPlan(
            action="capability_lookup", capability_query=_text(raw.get("capability_query"))
        )
    if action == "subagent_dispatch":
        tasks = _tasks(raw.get("tasks"))
        if not 2 <= len(tasks) <= 5:
            raise AgentPlanProtocolError("Planner subagent tasks are invalid")
        try:
            create_task_board({"tasks": list(tasks)}, user_text, depth=0)
        except ValueError as error:
            raise AgentPlanProtocolError("Planner subagent tasks are invalid") from error
        return AgentPlan(action="subagent_dispatch", tasks=tasks)
    raise AgentPlanProtocolError("Planner action is invalid")


def _tasks(value: object) -> tuple[dict[str, object], ...]:
    if not isinstance(value, list):
        return ()
    values = cast(list[object], value)
    return tuple(cast(dict[str, object], item) for item in values if isinstance(item, dict))


def _text(value: object) -> str | None:
    return value.strip() or None if isinstance(value, str) else None


def _direct() -> AgentPlan:
    return AgentPlan(action="direct_answer")
