from __future__ import annotations

import asyncio

from app.core.agent_runtime import AgentRuntimeProfile
from app.core.clock import SYSTEM_CLOCK
from app.infrastructure.db.session import DatabaseManager
from app.modules.agent_runtime.active_skill import (
    ActiveSkillCheckpointPort,
    SkillContextCheckpointPort,
)
from app.modules.agent_runtime.capability_session_factory import capability_session_for_request
from app.modules.agent_runtime.citation_hydration import SessionBoundCitationHydrator
from app.modules.agent_runtime.completed_taskboard_resume import prepare_completed_taskboard
from app.modules.agent_runtime.completion_loop import AgentCompletionLoop
from app.modules.agent_runtime.contracts import AgentModelPort, ChatMessage
from app.modules.agent_runtime.diagnostics import RuntimeDiagnostics
from app.modules.agent_runtime.execution_helpers import apply_controls
from app.modules.agent_runtime.final_renderer import FinalResponseRenderer
from app.modules.agent_runtime.finalization_checkpoint import (
    FinalizationCheckpointPort,
    VolatileFinalizationCheckpointStore,
)
from app.modules.agent_runtime.knowledge_execution import KnowledgeRequestExecutor
from app.modules.agent_runtime.knowledge_output import CitationInventoryHydratorPort
from app.modules.agent_runtime.math_runtime import BuiltinMathRuntime, MathRuntimePort
from app.modules.agent_runtime.mcp_executor import McpExecutor
from app.modules.agent_runtime.output import output_id
from app.modules.agent_runtime.pending_action import PendingToolActionPort
from app.modules.agent_runtime.pending_action_resume import PendingActionResumer
from app.modules.agent_runtime.plan_tools import append_capability_instruction, tools_for_plan
from app.modules.agent_runtime.planned_subagent_dispatch import dispatch_planned_subagents
from app.modules.agent_runtime.planner import AgentPlan, AgentPlanner
from app.modules.agent_runtime.prompt_composer import planning_input
from app.modules.agent_runtime.run_messages import messages_for_run
from app.modules.agent_runtime.runtime_budget import RuntimeExecutionBudget, execution_budget
from app.modules.agent_runtime.runtime_context import (
    load_conversation_history,
    load_resume_transcript,
    load_runtime_memory_context,
)
from app.modules.agent_runtime.script_runtime import ScriptRuntimePort
from app.modules.agent_runtime.skill_context_restore import restore_skill_context
from app.modules.agent_runtime.skill_executor import SkillExecutor
from app.modules.agent_runtime.subagent_dispatcher import SubagentDispatcherPort
from app.modules.agent_runtime.taskboard import completed_task_board
from app.modules.agent_runtime.time_runtime import BuiltinTimeRuntime, TimeRuntimePort
from app.modules.agent_runtime.tool_executor import RuntimeToolExecutor
from app.modules.agent_runtime.tool_rounds import ReplanResult
from app.modules.agent_runtime.turn_planning import (
    emit_plan_event,
    plan_turn,
)
from app.modules.capability_index.hybrid_search import CapabilitySearchRanker
from app.modules.interactions.history import ConversationHistoryPort
from app.modules.interactions.runtime import RuntimeEventSink, RuntimeRequest
from app.modules.knowledge.runtime import KnowledgeRuntimePort
from app.modules.memory.runtime import MemoryRuntimePort
from app.modules.schedules.runtime import ScheduleRuntimePort


class InProcessAgentRuntime:
    """Parrot's durable planner and tool loop, executed by RuntimeWorker."""

    def __init__(
        self,
        model: AgentModelPort,
        *,
        max_tool_rounds: int,
        max_tool_calls: int | None = None,
        max_consecutive_tool_errors: int = 3,
        max_model_retries: int = 2,
        max_control_plane_replans: int = 2,
        max_finalization_replans: int = 1,
        timeout_seconds: int,
        max_parallel_tool_calls: int = 3,
        capability_exact_repeat_limit: int = 1,
        capability_similar_repeat_limit: int = 2,
        capability_similarity_threshold: float = 0.6,
        capture_prompts: bool = False,
        history_turns: int = 12,
        history_max_tokens: int = 1_800,
        skill_executor: SkillExecutor | None = None,
        mcp_executor: McpExecutor | None = None,
        capability_search: CapabilitySearchRanker | None = None,
        memory_runtime: MemoryRuntimePort | None = None,
        knowledge_runtime: KnowledgeRuntimePort | None = None,
        conversation_history: ConversationHistoryPort | None = None,
        schedule_runtime: ScheduleRuntimePort | None = None,
        time_runtime: TimeRuntimePort | None = None,
        math_runtime: MathRuntimePort | None = None,
        script_runtime: ScriptRuntimePort | None = None,
        subagent_dispatcher: SubagentDispatcherPort | None = None,
        pending_actions: PendingToolActionPort | None = None,
        finalization_checkpoints: FinalizationCheckpointPort | None = None,
        active_skill_checkpoints: ActiveSkillCheckpointPort | None = None,
        skill_context_checkpoints: SkillContextCheckpointPort | None = None,
        citation_hydrator: CitationInventoryHydratorPort | None = None,
        database: DatabaseManager | None = None,
        max_supporting_skills: int = 3,
        max_subagent_tasks: int = 5,
        direct_rendering_enabled: bool = True,
        loop_subagents_enabled: bool = True,
    ) -> None:
        self._model = model
        self._max_tool_rounds = max_tool_rounds
        self._max_tool_calls = max_tool_calls or max_tool_rounds
        self._max_consecutive_tool_errors = max_consecutive_tool_errors
        self._max_model_retries = max_model_retries
        self._max_control_plane_replans = max_control_plane_replans
        self._max_finalization_replans = max_finalization_replans
        checkpoints = finalization_checkpoints or VolatileFinalizationCheckpointStore()
        self._final_renderer = FinalResponseRenderer(
            model,
            checkpoints,
            max_retries=max_model_retries,
        )
        self._planner = AgentPlanner(model, max_model_retries)
        self._timeout_seconds = timeout_seconds
        self._max_parallel_tool_calls = max_parallel_tool_calls
        self._capability_exact_repeat_limit = capability_exact_repeat_limit
        self._capability_similar_repeat_limit = capability_similar_repeat_limit
        self._capability_similarity_threshold = capability_similarity_threshold
        self._capture_prompts = capture_prompts
        self._history_turns = history_turns
        self._history_max_tokens = history_max_tokens
        self._skill_executor = skill_executor
        self._mcp_executor = mcp_executor
        self._capability_search = capability_search
        self._memory_runtime = memory_runtime
        self._knowledge_runtime = knowledge_runtime
        self._conversation_history = conversation_history
        self._schedule_runtime = schedule_runtime
        self._time_runtime = time_runtime or BuiltinTimeRuntime("UTC")
        self._math_runtime = math_runtime or BuiltinMathRuntime()
        self._script_runtime = script_runtime
        self._subagent_dispatcher = subagent_dispatcher
        self._pending_actions = pending_actions
        self._active_skill_checkpoints = active_skill_checkpoints
        self._skill_context_checkpoints = skill_context_checkpoints
        self._max_supporting_skills = max_supporting_skills
        self._max_subagent_tasks = max_subagent_tasks
        self._direct_rendering_enabled = direct_rendering_enabled
        self._loop_subagent_available = loop_subagents_enabled and subagent_dispatcher is not None
        self._pending_action_resumer = PendingActionResumer(
            pending_actions,
            self._final_renderer,
            skill_executor=skill_executor,
            mcp_executor=mcp_executor,
            capability_search=capability_search,
        )
        self._tool_executor = RuntimeToolExecutor(
            memory_runtime=self._memory_runtime,
            knowledge_runtime=self._knowledge_runtime,
            schedule_runtime=self._schedule_runtime,
            time_runtime=self._time_runtime,
            math_runtime=self._math_runtime,
            script_runtime=self._script_runtime,
            subagent_dispatcher=self._subagent_dispatcher,
            pending_actions=self._pending_actions,
            max_parallel_tool_calls=self._max_parallel_tool_calls,
            capability_exact_repeat_limit=self._capability_exact_repeat_limit,
            capability_similar_repeat_limit=self._capability_similar_repeat_limit,
            capability_similarity_threshold=self._capability_similarity_threshold,
        )
        self._completion_loop = AgentCompletionLoop(
            model,
            self._tool_executor,
            self._final_renderer,
            checkpoints,
            self._replan_after_control_plane_error,
            max_model_retries=max_model_retries,
            max_finalization_replans=max_finalization_replans,
            max_control_plane_replans=max_control_plane_replans,
            citation_hydrator=citation_hydrator
            or (SessionBoundCitationHydrator(database) if database is not None else None),
        )
        self._knowledge_executor = KnowledgeRequestExecutor(
            self._completion_loop,
            skill_executor=skill_executor,
            mcp_executor=mcp_executor,
            capability_search=capability_search,
            active_skill_checkpoints=active_skill_checkpoints,
            skill_context_checkpoints=skill_context_checkpoints,
            max_supporting_skills=max_supporting_skills,
        )

    async def execute(self, request: RuntimeRequest, events: RuntimeEventSink) -> None:
        if request.profile is None:
            raise ValueError("In-process agent runtime requires an agent runtime profile")
        self._model.validate(request.profile.llm)
        budget = execution_budget(
            request,
            timeout_seconds=self._timeout_seconds,
            max_tool_rounds=self._max_tool_rounds,
            max_tool_calls=self._max_tool_calls,
            max_consecutive_tool_errors=self._max_consecutive_tool_errors,
        )
        diagnostics = RuntimeDiagnostics(request, events, capture_prompts=self._capture_prompts)
        if request.enqueued_at is not None:
            queue_wait_ms = (SYSTEM_CLOCK.now() - request.enqueued_at).total_seconds() * 1_000
            await diagnostics.queue_wait(queue_wait_ms)
        async with asyncio.timeout(budget.timeout_seconds):
            if await self._completion_loop.resume(request, events, request.profile, diagnostics):
                return
            await self._run(request, events, budget, diagnostics)

    async def _run(
        self,
        request: RuntimeRequest,
        events: RuntimeEventSink,
        budget: RuntimeExecutionBudget,
        diagnostics: RuntimeDiagnostics,
    ) -> None:
        profile = request.profile
        if profile is None:
            raise ValueError("Agent runtime profile is missing")
        if request.pending_tool_action is not None:
            await self._pending_action_resumer.resume(request, events, profile, diagnostics)
            return
        user_text = request.text or ""
        runtime_memory, history, resume_transcript = await asyncio.gather(
            load_runtime_memory_context(request, self._memory_runtime),
            load_conversation_history(
                request,
                self._conversation_history,
                turns=self._history_turns,
                max_tokens=self._history_max_tokens,
            ),
            load_resume_transcript(
                request,
                self._conversation_history,
                max_tokens=self._history_max_tokens,
            ),
        )
        completed_board = completed_task_board(request.task_board)
        messages = messages_for_run(
            request,
            user_text,
            runtime_memory.reference,
            history,
            resume_transcript,
            agent_system_prompt=profile.system_prompt,
            is_knowledge_agent=profile.is_knowledge_only,
            has_completed_board=completed_board is not None,
        )
        if await apply_controls(request, events, messages):
            return
        if not profile.is_knowledge_only and not await restore_skill_context(
            request, events, profile, messages
        ):
            return
        planner_input = planning_input(user_text, request.resume_assistant_message, messages)
        await events.append(
            tenant_id=request.tenant_id,
            interaction_id=request.interaction_id,
            request_id=request.request_id,
            event_type="ai.input.processed",
            data={"interaction_id": request.interaction_id, "output_id": output_id(request)},
        )
        handled, resumed_loop_plan = await prepare_completed_taskboard(
            request,
            events,
            profile,
            messages,
            diagnostics,
            self._final_renderer,
            completed_board,
        )
        if handled:
            return
        if completed_board is None and profile.is_knowledge_only:
            await self._knowledge_executor.run(
                request,
                events,
                profile,
                messages,
                planner_input,
                budget,
                diagnostics,
                script_enabled=self._script_runtime is not None,
                subagent_enabled=self._loop_subagent_available,
                max_subagent_tasks=self._max_subagent_tasks,
                max_supporting_skills=self._max_supporting_skills,
            )
            return
        plan = resumed_loop_plan or await plan_turn(
            self._planner, request, profile, planner_input, diagnostics
        )
        if resumed_loop_plan is None:
            await emit_plan_event(request, events, plan)
        if (
            self._direct_rendering_enabled
            and plan.action == "direct_answer"
            and not profile.is_knowledge_only
            and request.runtime_depth == 0
        ):
            await self._final_renderer.render_new(
                request, events, profile, tuple(messages), diagnostics
            )
            return
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
        if plan.action == "subagent_dispatch":
            await dispatch_planned_subagents(self._subagent_dispatcher, request, events, plan.tasks)
            return
        append_capability_instruction(messages, plan)
        tools = tools_for_plan(
            request,
            plan,
            script_enabled=self._script_runtime is not None,
            subagent_enabled=self._loop_subagent_available,
            max_subagent_tasks=self._max_subagent_tasks,
            max_supporting_skills=self._max_supporting_skills,
        )
        await self._completion_loop.run(
            request,
            events,
            profile,
            messages,
            capabilities,
            tools,
            plan,
            budget,
            planner_input,
            diagnostics,
        )

    async def _replan_after_control_plane_error(
        self,
        request: RuntimeRequest,
        events: RuntimeEventSink,
        profile: AgentRuntimeProfile,
        messages: list[ChatMessage],
        planner_input: str,
        error_code: str,
        diagnostics: RuntimeDiagnostics | None,
    ) -> ReplanResult | None:
        messages.append(
            ChatMessage(
                role="system",
                content=(
                    "此前的工具请求失败，因为对应能力路由不可用"
                    f"（{error_code}）。不得重复调用该不可用路由。"
                ),
            )
        )
        if profile.is_knowledge_only:
            plan = AgentPlan(action="direct_answer", synthetic=True)
            await events.append(
                tenant_id=request.tenant_id,
                interaction_id=request.interaction_id,
                request_id=request.request_id,
                event_type="ai.agent.plan.created",
                data={
                    "action": plan.action,
                    "synthetic": plan.synthetic,
                    "reason": "control_plane_error",
                },
            )
            return ReplanResult(
                plan=plan,
                tools=tools_for_plan(
                    request,
                    plan,
                    script_enabled=self._script_runtime is not None,
                    subagent_enabled=self._loop_subagent_available,
                    max_subagent_tasks=self._max_subagent_tasks,
                    max_supporting_skills=self._max_supporting_skills,
                ),
            )
        plan = await self._planner.plan(
            profile,
            f"{planner_input}\n\nPrevious control-plane error: {error_code}",
            diagnostics,
        )
        await events.append(
            tenant_id=request.tenant_id,
            interaction_id=request.interaction_id,
            request_id=request.request_id,
            event_type="ai.agent.plan.created",
            data={
                "action": plan.action,
                "synthetic": plan.synthetic,
                "reason": "control_plane_error",
            },
        )
        if plan.action == "subagent_dispatch":
            await dispatch_planned_subagents(self._subagent_dispatcher, request, events, plan.tasks)
            return None
        append_capability_instruction(messages, plan)
        return ReplanResult(
            plan=plan,
            tools=tools_for_plan(
                request,
                plan,
                script_enabled=self._script_runtime is not None,
                subagent_enabled=self._loop_subagent_available,
                max_subagent_tasks=self._max_subagent_tasks,
                max_supporting_skills=self._max_supporting_skills,
            ),
        )
