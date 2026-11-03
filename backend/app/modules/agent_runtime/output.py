from __future__ import annotations

from app.modules.interactions.runtime import RuntimeEventSink, RuntimeRequest


def output_id(request: RuntimeRequest) -> str:
    if request.output_id:
        return request.output_id
    return f"output_{request.interaction_id}"


def thinking_id(request: RuntimeRequest, *, turn: int) -> str:
    return f"thinking_{request.interaction_id}_{turn}"


async def emit_delta(
    request: RuntimeRequest,
    events: RuntimeEventSink,
    delta: str,
    delta_index: int,
    *,
    value_output_id: str | None = None,
) -> None:
    await events.append(
        tenant_id=request.tenant_id,
        interaction_id=request.interaction_id,
        request_id=request.request_id,
        event_type="ai.output.delta",
        data={
            "output_id": value_output_id or output_id(request),
            "delta": delta,
            "delta_index": delta_index,
        },
    )


async def emit_thinking_delta(
    request: RuntimeRequest,
    events: RuntimeEventSink,
    delta: str,
    delta_index: int,
    *,
    value_thinking_id: str,
) -> None:
    await events.append(
        tenant_id=request.tenant_id,
        interaction_id=request.interaction_id,
        request_id=request.request_id,
        event_type="ai.thinking.delta",
        data={
            "thinking_id": value_thinking_id,
            "delta": delta,
            "delta_index": delta_index,
        },
    )


async def emit_thinking_completed(
    request: RuntimeRequest,
    events: RuntimeEventSink,
    content: str,
    *,
    value_thinking_id: str,
) -> None:
    await events.append(
        tenant_id=request.tenant_id,
        interaction_id=request.interaction_id,
        request_id=request.request_id,
        event_type="ai.thinking.completed",
        data={
            "thinking_id": value_thinking_id,
            "content": content,
        },
    )


async def reset_output(
    request: RuntimeRequest,
    events: RuntimeEventSink,
    *,
    value_output_id: str | None = None,
    reason: str | None = None,
) -> None:
    await events.append(
        tenant_id=request.tenant_id,
        interaction_id=request.interaction_id,
        request_id=request.request_id,
        event_type="ai.output.reset",
        data={
            "output_id": value_output_id or output_id(request),
            **({"reason": reason} if reason else {}),
        },
    )


async def emit_completed(
    request: RuntimeRequest,
    events: RuntimeEventSink,
    content: str,
    *,
    value_output_id: str | None = None,
    runtime_status: str = "completed",
    terminal_status: str = "completed",
    extra: dict[str, object] | None = None,
) -> None:
    await events.append(
        tenant_id=request.tenant_id,
        interaction_id=request.interaction_id,
        request_id=request.request_id,
        event_type="ai.output.completed",
        data={
            "output_id": value_output_id or output_id(request),
            "content": content,
            "runtime_status": runtime_status,
            **(extra or {}),
        },
        terminal_status=terminal_status,
    )


async def emit_waiting_for_user(
    request: RuntimeRequest, events: RuntimeEventSink, question: str
) -> None:
    await events.append(
        tenant_id=request.tenant_id,
        interaction_id=request.interaction_id,
        request_id=request.request_id,
        event_type="ai.output.completed",
        data={
            "output_id": output_id(request),
            "content": question,
            "runtime_status": "waiting_user_input",
        },
        terminal_status="waiting_user_input",
    )


async def emit_waiting_for_action(
    request: RuntimeRequest,
    events: RuntimeEventSink,
    action: dict[str, object],
) -> None:
    await events.append(
        tenant_id=request.tenant_id,
        interaction_id=request.interaction_id,
        request_id=request.request_id,
        event_type="ai.output.completed",
        data={
            "output_id": output_id(request),
            "content": "此操作需要你的明确确认。请选择批准或拒绝。",
            "runtime_status": "waiting_user_action",
            "action": {
                "action_id": action["action_id"],
                "action_hash": action["action_hash"],
                "version": action["version"],
                "choices": ["approve", "reject"],
            },
        },
        terminal_status="waiting_user_action",
    )
