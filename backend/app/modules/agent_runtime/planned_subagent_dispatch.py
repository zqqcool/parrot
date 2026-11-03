from __future__ import annotations

from app.modules.agent_runtime.output import emit_completed
from app.modules.agent_runtime.subagent_dispatcher import SubagentDispatcherPort
from app.modules.interactions.runtime import RuntimeEventSink, RuntimeRequest


async def dispatch_planned_subagents(
    dispatcher: SubagentDispatcherPort | None,
    request: RuntimeRequest,
    events: RuntimeEventSink,
    tasks: tuple[dict[str, object], ...],
) -> None:
    if dispatcher is None:
        await emit_completed(
            request,
            events,
            "I cannot delegate this task because the runtime subagent dispatcher is unavailable.",
        )
        return
    result = await dispatcher.dispatch(request, {"tasks": list(tasks)}, events)
    if result.get("status") != "waiting_subagents":
        await emit_completed(
            request,
            events,
            "I could not create a valid subagent plan for this request.",
        )
