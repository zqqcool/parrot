from __future__ import annotations

from app.core.agent_runtime import AgentRuntimeProfile
from app.modules.agent_runtime.contracts import ChatMessage
from app.modules.agent_runtime.output import emit_completed
from app.modules.agent_runtime.prompt_composer import insert_skill_context
from app.modules.agent_runtime.skill_context_profiles import (
    current_skill_context,
    primary_skill_profile,
    supporting_skill_profiles,
)
from app.modules.interactions.runtime import RuntimeEventSink, RuntimeRequest


async def restore_skill_context(
    request: RuntimeRequest,
    events: RuntimeEventSink,
    profile: AgentRuntimeProfile,
    messages: list[ChatMessage],
) -> bool:
    context = current_skill_context(request.skill_context, request.active_skill)
    if context.primary is None and not context.supporting:
        return True
    primary = primary_skill_profile(profile.skills, context.primary)
    supporting = supporting_skill_profiles(profile.skills, context)
    if (context.primary is not None and primary is None) or len(supporting) != len(
        context.supporting
    ):
        await emit_completed(
            request,
            events,
            "无法恢复此前固定的 Skill Context，系统没有切换到其他版本。",
            runtime_status="partial",
            terminal_status="partial",
            extra={"partial_reason": "skill_context_version_unavailable"},
        )
        return False
    insert_skill_context(messages, request.interaction_id, primary, supporting)
    return True
