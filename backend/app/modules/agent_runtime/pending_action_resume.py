from __future__ import annotations

from typing import cast

from app.core.agent_runtime import AgentRuntimeProfile
from app.modules.agent_runtime.capability_session_factory import capability_session_for_request
from app.modules.agent_runtime.contracts import ChatMessage, ToolCall
from app.modules.agent_runtime.diagnostics import RuntimeDiagnostics
from app.modules.agent_runtime.final_renderer import FinalResponseRenderer
from app.modules.agent_runtime.mcp_executor import McpExecutor
from app.modules.agent_runtime.model_observation import tool_result_message
from app.modules.agent_runtime.output import emit_completed, emit_waiting_for_action
from app.modules.agent_runtime.pending_action import PendingToolActionPort
from app.modules.agent_runtime.resume_snapshot import restore_resume_snapshot
from app.modules.agent_runtime.skill_executor import SkillExecutor
from app.modules.capability_index.hybrid_search import CapabilitySearchRanker
from app.modules.interactions.runtime import RuntimeEventSink, RuntimeRequest


class PendingActionResumer:
    """Resumes one persisted approval without rerunning the agent loop."""

    def __init__(
        self,
        pending_actions: PendingToolActionPort | None,
        final_renderer: FinalResponseRenderer,
        *,
        skill_executor: SkillExecutor | None,
        mcp_executor: McpExecutor | None,
        capability_search: CapabilitySearchRanker | None,
    ) -> None:
        self._pending_actions = pending_actions
        self._final_renderer = final_renderer
        self._skill_executor = skill_executor
        self._mcp_executor = mcp_executor
        self._capability_search = capability_search

    async def resume(
        self,
        request: RuntimeRequest,
        events: RuntimeEventSink,
        profile: AgentRuntimeProfile,
        diagnostics: RuntimeDiagnostics,
    ) -> None:
        action = request.pending_tool_action
        if action is None:
            return
        status = action.get("status")
        if status == "pending":
            await _emit_pending_again(request, events, action)
            return
        if status in {"rejected", "expired"}:
            message = (
                "该操作已过期，未执行。" if status == "expired" else "该操作已被拒绝，未执行。"
            )
            await emit_completed(request, events, message)
            return
        if status == "executing":
            await _emit_uncertain(request, events)
            return
        result = _mapping_or_none(action.get("result"))
        if status == "approved":
            result = await self._execute_approved(request, profile, action)
        if result is None:
            await _emit_invalid_resume(request, events)
            return
        messages = _resume_messages(action, result)
        if not messages:
            await emit_completed(
                request,
                events,
                "操作已经处理，但缺少可安全恢复的上下文。",
                runtime_status="partial",
                terminal_status="partial",
                extra={"partial_reason": "pending_action_context_invalid"},
            )
            return
        succeeded = result.get("status") in {"ok", "succeeded"}
        await self._final_renderer.render_new(
            request,
            events,
            profile,
            tuple(messages),
            diagnostics,
            terminal_status="completed" if succeeded else "partial",
            completion_data=({} if succeeded else {"partial_reason": "approved_action_failed"}),
        )

    async def _execute_approved(
        self,
        request: RuntimeRequest,
        profile: AgentRuntimeProfile,
        action: dict[str, object],
    ) -> dict[str, object] | None:
        if self._pending_actions is None:
            return None
        if not await self._pending_actions.mark_executing(request, action):
            return None
        capability_id = action.get("capability_id")
        arguments = action.get("arguments")
        schema_hash = action.get("schema_hash")
        if (
            not isinstance(capability_id, str)
            or not isinstance(arguments, dict)
            or not isinstance(schema_hash, str)
        ):
            return None
        capabilities = capability_session_for_request(
            profile,
            request,
            skill_executor=self._skill_executor,
            mcp_executor=self._mcp_executor,
            search_ranker=self._capability_search,
        )
        result = await capabilities.execute_approved(
            capability_id,
            cast(dict[str, object], arguments),
            schema_hash,
        )
        await self._pending_actions.mark_completed(request, action, result)
        return result


async def _emit_pending_again(
    request: RuntimeRequest,
    events: RuntimeEventSink,
    action: dict[str, object],
) -> None:
    if all(isinstance(action.get(key), str) for key in ("action_id", "action_hash", "version")):
        await emit_waiting_for_action(request, events, action)
        return
    await _emit_invalid_resume(request, events)


async def _emit_invalid_resume(request: RuntimeRequest, events: RuntimeEventSink) -> None:
    await emit_completed(
        request,
        events,
        "无法恢复已确认的操作，且系统未执行该操作。",
        runtime_status="partial",
        terminal_status="partial",
        extra={"partial_reason": "pending_action_resume_invalid"},
    )


async def _emit_uncertain(request: RuntimeRequest, events: RuntimeEventSink) -> None:
    await emit_completed(
        request,
        events,
        "操作结果状态不确定；为避免重复产生副作用，系统没有自动重试。",
        runtime_status="partial",
        terminal_status="partial",
        extra={"partial_reason": "pending_action_execution_uncertain"},
    )


def _resume_messages(action: dict[str, object], result: dict[str, object]) -> list[ChatMessage]:
    raw_messages = action.get("resume_messages")
    call_id = action.get("call_id")
    capability_id = action.get("capability_id")
    arguments = action.get("arguments")
    if (
        not isinstance(raw_messages, list)
        or not isinstance(call_id, str)
        or not isinstance(capability_id, str)
        or not isinstance(arguments, dict)
    ):
        return []
    values: list[dict[str, object]] = []
    for raw in cast(list[object], raw_messages):
        if not isinstance(raw, dict):
            return []
        values.append(cast(dict[str, object], raw))
    try:
        messages = restore_resume_snapshot(tuple(values))
    except ValueError:
        return []
    call = ToolCall(
        id=call_id,
        name="capability_execute",
        arguments={
            "skill_id": capability_id,
            "input": cast(dict[str, object], arguments),
        },
    )
    messages.extend(
        (
            ChatMessage(role="assistant", content=None, tool_calls=(call,)),
            ChatMessage(
                role="tool",
                content=tool_result_message(result),
                name=call.name,
                tool_call_id=call.id,
            ),
        )
    )
    return messages


def _mapping_or_none(value: object) -> dict[str, object] | None:
    return cast(dict[str, object], value) if isinstance(value, dict) else None
