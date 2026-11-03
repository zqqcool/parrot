from __future__ import annotations

from app.modules.agent_runtime.builtin_tools import (
    knowledge_search_tool,
    runtime_builtin_tools,
    schedule_tool,
    script_tool,
)
from app.modules.agent_runtime.capability_tools import capability_tools
from app.modules.agent_runtime.contracts import ChatMessage, ToolDefinition
from app.modules.agent_runtime.delegation_gate import can_dispatch_from_loop
from app.modules.agent_runtime.execution_helpers import (
    can_manage_schedules,
    can_request_user_input,
)
from app.modules.agent_runtime.final_response import ask_user_tool, final_response_tool
from app.modules.agent_runtime.planner import AgentPlan
from app.modules.agent_runtime.subagent_tools import subagent_dispatch_tool
from app.modules.interactions.runtime import RuntimeRequest


def tools_for_plan(
    request: RuntimeRequest,
    plan: AgentPlan,
    *,
    script_enabled: bool,
    subagent_enabled: bool = False,
    max_subagent_tasks: int = 5,
    max_supporting_skills: int = 3,
) -> tuple[ToolDefinition, ...]:
    profile = request.profile
    if profile is not None and profile.is_knowledge_only:
        tools = runtime_builtin_tools() + (knowledge_search_tool(),)
        if profile.skills or profile.mcp_servers:
            tools += capability_tools()
        if subagent_enabled and can_dispatch_from_loop(request, plan):
            tools += (subagent_dispatch_tool(max_subagent_tasks, max_supporting_skills),)
        if profile.skills and can_request_user_input(request):
            tools += (final_response_tool(),)
        return _with_user_input_tool(request, tools)
    if profile is not None and not profile.allows_runtime_tools:
        return _with_user_input_tool(request, ())
    tools = runtime_builtin_tools()
    if script_enabled and request.runtime_depth == 0:
        tools += (script_tool(),)
    if plan.action == "capability_lookup":
        tools += capability_tools()
    if subagent_enabled and can_dispatch_from_loop(request, plan):
        tools += (subagent_dispatch_tool(max_subagent_tasks, max_supporting_skills),)
    if can_manage_schedules(request):
        tools += (schedule_tool(),)
    return _with_user_input_tool(request, tools)


def _with_user_input_tool(
    request: RuntimeRequest, tools: tuple[ToolDefinition, ...]
) -> tuple[ToolDefinition, ...]:
    return tools + (ask_user_tool(),) if can_request_user_input(request) else tools


def append_capability_instruction(messages: list[ChatMessage], plan: AgentPlan) -> None:
    if plan.action != "capability_lookup":
        return
    if plan.synthetic:
        if plan.capability_prefetched:
            return
        messages.append(
            ChatMessage(
                role="system",
                content=(
                    "当前知识型 Agent 已绑定可用能力。回答前必须先调用 capability_search："
                    "需要按当前问题检索并加载 Skill 时使用 action=find_and_load 且提供非空 query；"
                    "仅需列出可用能力时使用 action=find 且 query 为空。instruction-only Skill"
                    "加载后须再调用 capability_execute 获取指令并据此回答。instruction-only Skill"
                    "不会启动沙盒，且不得声称发生了外部执行。"
                ),
            )
        )
        return
    if not plan.capability_query:
        return
    messages.append(
        ChatMessage(
            role="system",
            content=(
                "已选择能力检索。优先使用 capability_search 的 find_and_load 操作完成检索并加载"
                "顶层 Skill，再调用 capability_execute；能力级查询为："
                f"{plan.capability_query}"
            ),
        )
    )
