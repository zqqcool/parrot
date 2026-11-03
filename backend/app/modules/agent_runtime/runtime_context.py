from __future__ import annotations

from dataclasses import dataclass

from app.modules.agent_runtime.execution_helpers import memory_context as request_memory_context
from app.modules.interactions.history import (
    ConversationHistoryContext,
    ConversationHistoryMessage,
    ConversationHistoryPort,
    ConversationTurn,
)
from app.modules.interactions.runtime import RuntimeRequest
from app.modules.memory.context import (
    MemoryContextItem,
    MemoryRecallContext,
    build_memory_item_context,
)
from app.modules.memory.runtime import AutomaticMemoryRuntimePort, MemoryRuntimePort


@dataclass(frozen=True)
class RuntimeMemoryContext:
    reference: str = ""
    pinned_items: tuple[MemoryContextItem, ...] = ()


async def load_memory_context(request: RuntimeRequest, runtime: MemoryRuntimePort | None) -> str:
    if runtime is None:
        return ""
    return await runtime.context_for(request_memory_context(request))


async def load_runtime_memory_context(
    request: RuntimeRequest, runtime: MemoryRuntimePort | None
) -> RuntimeMemoryContext:
    if runtime is None:
        return RuntimeMemoryContext()
    context = request_memory_context(request)
    if isinstance(runtime, AutomaticMemoryRuntimePort):
        items = await runtime.pinned_for(context)
        return RuntimeMemoryContext(
            reference=build_memory_item_context(items, 400),
            pinned_items=items,
        )
    return RuntimeMemoryContext(reference=await runtime.context_for(context))


async def recall_memory_context(
    request: RuntimeRequest,
    runtime: MemoryRuntimePort | None,
    query: str,
) -> MemoryRecallContext:
    if runtime is None or not isinstance(runtime, AutomaticMemoryRuntimePort):
        return MemoryRecallContext()
    return await runtime.recall_for(request_memory_context(request), query)


async def load_conversation_history(
    request: RuntimeRequest,
    history: ConversationHistoryPort | None,
    *,
    turns: int,
    max_tokens: int,
) -> tuple[ConversationTurn, ...]:
    if history is None or request.runtime_depth > 0:
        return ()
    items = await history.recent(
        ConversationHistoryContext(
            tenant_id=request.tenant_id,
            agent_id=request.agent_id,
            actor_type=request.actor_type,
            actor_id=request.actor_id,
            interaction_id=request.interaction_id,
            conversation_id=request.conversation_id,
        ),
        turns=turns,
        max_tokens=max_tokens,
    )
    return items


async def load_resume_transcript(
    request: RuntimeRequest,
    history: ConversationHistoryPort | None,
    *,
    max_tokens: int,
) -> tuple[ConversationHistoryMessage, ...]:
    if (
        history is None
        or request.runtime_depth > 0
        or not request.resume_assistant_message
        or request.control_after_sequence <= 0
    ):
        return ()
    return await history.resume_messages(
        ConversationHistoryContext(
            tenant_id=request.tenant_id,
            agent_id=request.agent_id,
            actor_type=request.actor_type,
            actor_id=request.actor_id,
            interaction_id=request.interaction_id,
            conversation_id=request.conversation_id,
        ),
        through_sequence=request.control_after_sequence,
        max_tokens=max_tokens,
    )
