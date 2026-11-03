from __future__ import annotations

from app.core.agent_runtime import AgentRuntimeProfile
from app.modules.agent_runtime.active_skill import (
    ActiveSkillCheckpointPort,
    SkillContextCheckpointPort,
)
from app.modules.agent_runtime.capabilities import CapabilitySession
from app.modules.agent_runtime.mcp_executor import McpExecutor
from app.modules.agent_runtime.skill_executor import SkillExecutionContext, SkillExecutor
from app.modules.capability_index.hybrid_search import CapabilitySearchRanker
from app.modules.interactions.runtime import RuntimeRequest, RuntimeSkillContext


def capability_session_for_request(
    profile: AgentRuntimeProfile,
    request: RuntimeRequest,
    *,
    skill_executor: SkillExecutor | None,
    mcp_executor: McpExecutor | None,
    search_ranker: CapabilitySearchRanker | None = None,
    active_skill_checkpoints: ActiveSkillCheckpointPort | None = None,
    skill_context_checkpoints: SkillContextCheckpointPort | None = None,
    max_supporting_skills: int = 3,
) -> CapabilitySession:
    context = request.skill_context or RuntimeSkillContext(primary=request.active_skill)
    pinned = ((context.primary,) if context.primary is not None else ()) + context.supporting
    return CapabilitySession(
        profile.skills,
        mcp_servers=profile.mcp_servers,
        minimum_relevance_score=profile.capability_relevance_threshold,
        loaded_skill_ids={item.skill_id for item in pinned},
        active_skill=context.primary,
        skill_context=context,
        max_supporting_skills=max_supporting_skills,
        active_skill_checkpoints=active_skill_checkpoints,
        skill_context_checkpoints=skill_context_checkpoints,
        skill_executor=skill_executor,
        execution_context=SkillExecutionContext(
            tenant_id=request.tenant_id,
            interaction_id=request.interaction_id,
            actor_type=request.actor_type,
            actor_id=request.actor_id,
            request_id=request.request_id,
        ),
        mcp_executor=mcp_executor,
        search_ranker=search_ranker,
        knowledge_only=profile.is_knowledge_only,
        approval_supported=(
            request.runtime_depth == 0 and request.entry_type not in {"schedule", "subagent"}
        ),
    )
