from __future__ import annotations

from app.core.agent_runtime import AgentRuntimeProfile
from app.modules.agent_runtime.diagnostics import RuntimeDiagnostics
from app.modules.agent_runtime.planner import AgentPlan, AgentPlanner
from app.modules.agent_runtime.subagent_plan import synthetic_subagent_plan
from app.modules.interactions.runtime import RuntimeEventSink, RuntimeRequest


async def plan_turn(
    planner: AgentPlanner,
    request: RuntimeRequest,
    profile: AgentRuntimeProfile,
    planner_input: str,
    diagnostics: RuntimeDiagnostics,
) -> AgentPlan:
    if profile.is_knowledge_only:
        return AgentPlan(action="direct_answer", synthetic=True)
    if request.runtime_depth > 0 or request.subagent_task is not None:
        return synthetic_subagent_plan(
            request.subagent_task,
            has_capabilities=bool(profile.skills or profile.mcp_servers),
        )
    return await planner.plan(profile, planner_input, diagnostics)


async def emit_plan_event(
    request: RuntimeRequest, events: RuntimeEventSink, plan: AgentPlan
) -> None:
    await events.append(
        tenant_id=request.tenant_id,
        interaction_id=request.interaction_id,
        request_id=request.request_id,
        event_type="ai.agent.plan.created",
        data={"action": plan.action, "synthetic": plan.synthetic},
    )
