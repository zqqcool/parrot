from __future__ import annotations

from app.modules.agent_runtime.capabilities import CapabilitySession
from app.modules.agent_runtime.contracts import ChatMessage, ToolCall
from app.modules.agent_runtime.knowledge_output import (
    attachment_media_for_result,
    catalog_for_model,
    inventory_from_evidence,
)
from app.modules.agent_runtime.math_runtime import MathRuntimePort
from app.modules.agent_runtime.output import output_id
from app.modules.agent_runtime.script_runtime import ScriptRuntimePort
from app.modules.agent_runtime.subagent_dispatcher import SubagentDispatcherPort
from app.modules.agent_runtime.subagent_task_prompt import render_results
from app.modules.agent_runtime.taskboard import completed_task_board
from app.modules.agent_runtime.time_runtime import TimeRuntimePort
from app.modules.agent_runtime.todos import update_todos
from app.modules.interactions.runtime import RuntimeEventSink, RuntimeRequest
from app.modules.knowledge.runtime import KnowledgeRuntimeContext, KnowledgeRuntimePort
from app.modules.memory.runtime import MemoryRuntimeContext, MemoryRuntimePort
from app.modules.schedules.runtime import ScheduleRuntimeContext, ScheduleRuntimePort


async def apply_controls(
    request: RuntimeRequest,
    events: RuntimeEventSink,
    messages: list[ChatMessage],
    *,
    value_output_id: str | None = None,
) -> bool:
    if request.control_reader is None:
        return False
    controls = await request.control_reader.consume(request)
    if controls.cancel_requested:
        await events.append(
            tenant_id=request.tenant_id,
            interaction_id=request.interaction_id,
            request_id=request.request_id,
            event_type="ai.output.cancelled",
            data={
                "finish_reason": "cancelled",
                "output_id": value_output_id or output_id(request),
            },
            terminal_status="cancelled",
        )
        return True
    for message in controls.steering_messages:
        messages.append(ChatMessage(role="user", content=message))
        await events.append(
            tenant_id=request.tenant_id,
            interaction_id=request.interaction_id,
            request_id=request.request_id,
            event_type="ai.interaction.steer.accepted",
            data={"message": message},
        )
    return False


async def tool_result(
    call: ToolCall,
    capabilities: CapabilitySession,
    memory_runtime: MemoryRuntimePort | None,
    knowledge_runtime: KnowledgeRuntimePort | None,
    schedule_runtime: ScheduleRuntimePort | None,
    time_runtime: TimeRuntimePort | None,
    math_runtime: MathRuntimePort | None,
    script_runtime: ScriptRuntimePort | None,
    subagent_dispatcher: SubagentDispatcherPort | None,
    request: RuntimeRequest,
    events: RuntimeEventSink,
    todos: list[dict[str, str]],
    messages: list[ChatMessage],
) -> dict[str, object]:
    if call.name == "knowledge_search":
        return await _knowledge_result(call, knowledge_runtime, request)
    if call.name in {"memory", "todo", "time", "math"}:
        return await _builtin_result(
            call, memory_runtime, time_runtime, math_runtime, request, events, todos
        )
    if call.name == "script":
        return await _script_result(call, script_runtime)
    if call.name in {"subagent_dispatch", "schedule"}:
        return await _orchestration_result(
            call, schedule_runtime, subagent_dispatcher, request, events, messages
        )
    return await _capability_result(call, capabilities)


async def _knowledge_result(
    call: ToolCall,
    knowledge_runtime: KnowledgeRuntimePort | None,
    request: RuntimeRequest,
) -> dict[str, object]:
    if knowledge_runtime is None:
        return {"status": "rejected", "code": "KNOWLEDGE_SEARCH_NOT_ENABLED"}
    query = call.arguments.get("query")
    raw_limit = call.arguments.get("limit", 6)
    if not isinstance(query, str) or not query.strip() or len(query) > 1_000:
        return {"status": "rejected", "code": "KNOWLEDGE_QUERY_INVALID"}
    if isinstance(raw_limit, bool) or not isinstance(raw_limit, int) or not 1 <= raw_limit <= 12:
        return {"status": "rejected", "code": "KNOWLEDGE_LIMIT_INVALID"}
    evidence = await knowledge_runtime.retrieve(
        KnowledgeRuntimeContext(
            tenant_id=request.tenant_id,
            agent_id=request.agent_id,
            query=query.strip(),
            limit=raw_limit,
        )
    )
    if evidence.status == "unavailable":
        return {"status": "failed", "code": "KNOWLEDGE_SEARCH_UNAVAILABLE"}
    inventory = inventory_from_evidence(evidence.items)
    return {
        "status": "ok",
        "retrieval_status": evidence.status,
        "citations": catalog_for_model(inventory),
        "citation_ids": list(evidence.citation_ids),
        "evidence": evidence.content,
        "duration_ms": evidence.duration_ms,
        "embed_duration_ms": evidence.embed_duration_ms,
        "space_count": evidence.space_count,
        "retrieval_method": evidence.retrieval_method,
        "_attachment_media": attachment_media_for_result(inventory),
    }


async def _builtin_result(
    call: ToolCall,
    memory_runtime: MemoryRuntimePort | None,
    time_runtime: TimeRuntimePort | None,
    math_runtime: MathRuntimePort | None,
    request: RuntimeRequest,
    events: RuntimeEventSink,
    todos: list[dict[str, str]],
) -> dict[str, object]:
    if call.name == "memory":
        if memory_runtime is None:
            return {"status": "rejected", "code": "MEMORY_NOT_ENABLED"}
        return await memory_runtime.handle(memory_context(request), call.arguments)
    if call.name == "todo":
        result = update_todos(todos, call.arguments)
        await events.append(
            tenant_id=request.tenant_id,
            interaction_id=request.interaction_id,
            request_id=request.request_id,
            event_type="ai.agent.todo.updated",
            data={"todos": result.get("todos", []), "summary": result.get("summary", {})},
        )
        return result
    if call.name == "time":
        if time_runtime is None:
            return {"status": "rejected", "code": "TIME_NOT_ENABLED"}
        return await time_runtime.handle(call.arguments)
    if math_runtime is None:
        return {"status": "rejected", "code": "MATH_NOT_ENABLED"}
    return await math_runtime.handle(call.arguments)


async def _orchestration_result(
    call: ToolCall,
    schedule_runtime: ScheduleRuntimePort | None,
    subagent_dispatcher: SubagentDispatcherPort | None,
    request: RuntimeRequest,
    events: RuntimeEventSink,
    messages: list[ChatMessage],
) -> dict[str, object]:
    if call.name == "subagent_dispatch":
        if subagent_dispatcher is None:
            return {"status": "rejected", "code": "SUBAGENT_DISPATCH_NOT_ENABLED"}
        return await subagent_dispatcher.dispatch(
            request,
            call.arguments,
            events,
            resume_messages=messages,
            source="agent_loop",
            dispatch_call_id=call.id,
        )
    if schedule_runtime is None:
        return {"status": "rejected", "code": "SCHEDULE_NOT_ENABLED"}
    return await schedule_runtime.handle(schedule_context(request), call.arguments)


async def _script_result(
    call: ToolCall, script_runtime: ScriptRuntimePort | None
) -> dict[str, object]:
    if script_runtime is None:
        return {"status": "rejected", "code": "SCRIPT_EXECUTION_DISABLED"}
    return await script_runtime.handle(call.arguments)


async def _capability_result(call: ToolCall, capabilities: CapabilitySession) -> dict[str, object]:
    capability_id = call.arguments.get("capability_id")
    if capability_id is None:
        capability_id = call.arguments.get("skill_id")
    if call.name == "capability_search":
        return await capabilities.search(
            call.arguments.get("action"),
            call.arguments.get("query"),
            capability_id,
            call.arguments.get("role", "primary"),
        )
    if call.name == "capability_execute":
        return await capabilities.execute(capability_id, call.arguments.get("input"))
    return {"status": "rejected", "code": "TOOL_NOT_AVAILABLE"}


def memory_context(request: RuntimeRequest) -> MemoryRuntimeContext:
    return MemoryRuntimeContext(
        tenant_id=request.tenant_id,
        agent_id=request.agent_id,
        actor_type=request.actor_type,
        actor_id=request.actor_id,
        interaction_id=request.interaction_id,
        conversation_id=request.conversation_id,
    )


def can_manage_schedules(request: RuntimeRequest) -> bool:
    return request.runtime_depth == 0 and request.entry_type not in {"schedule", "subagent"}


def can_request_user_input(request: RuntimeRequest) -> bool:
    return request.runtime_depth == 0 and request.entry_type == "websocket"


def schedule_context(request: RuntimeRequest) -> ScheduleRuntimeContext:
    return ScheduleRuntimeContext(
        tenant_id=request.tenant_id,
        agent_id=request.agent_id,
        actor_type=request.actor_type,
        actor_id=request.actor_id,
        interaction_id=request.interaction_id,
        request_id=request.request_id,
        latest_user_text=request.text or "",
    )


def taskboard_context(value: dict[str, object] | None) -> str:
    board = completed_task_board(value)
    return render_results(board) if board is not None else ""
