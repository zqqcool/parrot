from __future__ import annotations

from app.core.agent_runtime import AgentRuntimeProfile
from app.modules.agent_runtime.active_skill import (
    ActiveSkillCheckpointPort,
    SkillContextCheckpointPort,
)
from app.modules.agent_runtime.capability_session_factory import capability_session_for_request
from app.modules.agent_runtime.completion_loop import AgentCompletionLoop
from app.modules.agent_runtime.contracts import ChatMessage
from app.modules.agent_runtime.diagnostics import RuntimeDiagnostics
from app.modules.agent_runtime.mcp_executor import McpExecutor
from app.modules.agent_runtime.output import emit_completed
from app.modules.agent_runtime.plan_tools import tools_for_plan
from app.modules.agent_runtime.planner import AgentPlan
from app.modules.agent_runtime.prompt_composer import insert_skill_context
from app.modules.agent_runtime.runtime_budget import RuntimeExecutionBudget
from app.modules.agent_runtime.skill_context_profiles import (
    current_skill_context,
    primary_skill_profile,
    supporting_skill_profiles,
)
from app.modules.agent_runtime.skill_executor import SkillExecutor
from app.modules.agent_runtime.turn_planning import emit_plan_event
from app.modules.capability_index.hybrid_search import CapabilitySearchRanker
from app.modules.interactions.runtime import RuntimeEventSink, RuntimeRequest


class KnowledgeRequestExecutor:
    """Runs a knowledge request directly in the shared root completion loop."""

    def __init__(
        self,
        completion_loop: AgentCompletionLoop,
        *,
        skill_executor: SkillExecutor | None,
        mcp_executor: McpExecutor | None,
        capability_search: CapabilitySearchRanker | None,
        active_skill_checkpoints: ActiveSkillCheckpointPort | None,
        skill_context_checkpoints: SkillContextCheckpointPort | None,
        max_supporting_skills: int,
    ) -> None:
        self._completion_loop = completion_loop
        self._skill_executor = skill_executor
        self._mcp_executor = mcp_executor
        self._capability_search = capability_search
        self._active_skill_checkpoints = active_skill_checkpoints
        self._skill_context_checkpoints = skill_context_checkpoints
        self._max_supporting_skills = max_supporting_skills

    async def run(
        self,
        request: RuntimeRequest,
        events: RuntimeEventSink,
        profile: AgentRuntimeProfile,
        messages: list[ChatMessage],
        planner_input: str,
        budget: RuntimeExecutionBudget,
        diagnostics: RuntimeDiagnostics,
        *,
        script_enabled: bool,
        subagent_enabled: bool,
        max_subagent_tasks: int,
        max_supporting_skills: int,
    ) -> None:
        capabilities = capability_session_for_request(
            profile,
            request,
            skill_executor=self._skill_executor,
            mcp_executor=self._mcp_executor,
            search_ranker=self._capability_search,
            active_skill_checkpoints=self._active_skill_checkpoints,
            skill_context_checkpoints=self._skill_context_checkpoints,
            max_supporting_skills=self._max_supporting_skills,
        )
        skill_context = current_skill_context(capabilities.skill_context, capabilities.active_skill)
        active_skill = primary_skill_profile(capabilities.skills, skill_context.primary)
        supporting_skills = supporting_skill_profiles(capabilities.skills, skill_context)
        expected_supporting = len(skill_context.supporting)
        if (skill_context.primary is not None and active_skill is None) or len(
            supporting_skills
        ) != expected_supporting:
            partial_reason = (
                "active_skill_version_unavailable"
                if not skill_context.supporting
                else "skill_context_version_unavailable"
            )
            await emit_completed(
                request,
                events,
                "无法恢复此前固定的 Skill Context，系统没有切换到其他版本。",
                runtime_status="partial",
                terminal_status="partial",
                extra={"partial_reason": partial_reason},
            )
            return
        if active_skill is not None or supporting_skills:
            insert_skill_context(
                messages,
                request.interaction_id,
                active_skill,
                supporting_skills,
            )
        context_restored = active_skill is not None or bool(supporting_skills)
        plan = AgentPlan(
            action=("capability_lookup" if context_restored else "agent_loop"),
            synthetic=True,
            capability_prefetched=context_restored,
        )
        await emit_plan_event(request, events, plan)
        await self._completion_loop.run(
            request,
            events,
            profile,
            messages,
            capabilities,
            tools_for_plan(
                request,
                plan,
                script_enabled=script_enabled,
                subagent_enabled=subagent_enabled,
                max_subagent_tasks=max_subagent_tasks,
                max_supporting_skills=max_supporting_skills,
            ),
            plan,
            budget,
            planner_input,
            diagnostics,
        )
