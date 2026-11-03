from __future__ import annotations

from app.core.agent_runtime import AgentRuntimeProfile
from app.modules.agent_runtime.contracts import ChatMessage
from app.modules.agent_runtime.diagnostics import RuntimeDiagnostics
from app.modules.agent_runtime.final_renderer import FinalResponseRenderer
from app.modules.agent_runtime.output import emit_completed
from app.modules.agent_runtime.planner import AgentPlan
from app.modules.agent_runtime.resume_snapshot import restore_resume_snapshot
from app.modules.agent_runtime.subagent_continuation import (
    is_loop_taskboard,
    resumed_plan,
    subagent_terminal_metadata,
)
from app.modules.agent_runtime.taskboard import TaskBoard
from app.modules.agent_runtime.turn_planning import emit_plan_event
from app.modules.interactions.runtime import RuntimeEventSink, RuntimeRequest


async def prepare_completed_taskboard(
    request: RuntimeRequest,
    events: RuntimeEventSink,
    profile: AgentRuntimeProfile,
    messages: list[ChatMessage],
    diagnostics: RuntimeDiagnostics,
    renderer: FinalResponseRenderer,
    board: TaskBoard | None,
) -> tuple[bool, AgentPlan | None]:
    if board is None:
        return False, None
    loop_plan = resumed_plan(board) if is_loop_taskboard(board) else None
    if loop_plan is not None and not _valid_resume_snapshot(request):
        await emit_completed(
            request,
            events,
            "无法安全恢复 Subagent 派发前的上下文，本次运行已停止。",
            runtime_status="partial",
            terminal_status="partial",
            extra={"partial_reason": "subagent_resume_context_invalid"},
        )
        return True, None
    await emit_plan_event(
        request,
        events,
        loop_plan or AgentPlan(action="direct_answer", synthetic=True),
    )
    if loop_plan is not None:
        return False, loop_plan
    terminal_status, completion_data = subagent_terminal_metadata(request.task_board)
    await renderer.render_new(
        request,
        events,
        profile,
        tuple(messages),
        diagnostics,
        terminal_status=terminal_status,
        completion_data=completion_data,
    )
    return True, None


def _valid_resume_snapshot(request: RuntimeRequest) -> bool:
    if not request.resume_messages:
        return False
    try:
        return bool(restore_resume_snapshot(request.resume_messages))
    except ValueError:
        return False
