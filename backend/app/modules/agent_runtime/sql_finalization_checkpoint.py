from __future__ import annotations

from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import new_id
from app.infrastructure.db.session import DatabaseManager
from app.modules.agent_runtime.contracts import ChatMessage, ToolCall
from app.modules.agent_runtime.finalization_checkpoint import (
    FinalizationCheckpoint,
    FinalizationCheckpointPort,
    FinalizationDeliveryMode,
    validate_candidate,
)
from app.modules.interactions.models import Interaction, InteractionFinalization
from app.modules.interactions.runtime import RuntimeRequest


class SqlFinalizationCheckpointStore(FinalizationCheckpointPort):
    def __init__(self, database: DatabaseManager) -> None:
        self._database = database

    async def prepare(
        self,
        request: RuntimeRequest,
        messages: tuple[ChatMessage, ...],
        *,
        terminal_status: str,
        completion_data: dict[str, object],
    ) -> FinalizationCheckpoint:
        async with self._database.session() as session:
            await self._database.set_tenant(session, request.tenant_id)
            interaction = await _interaction(session, request)
            item = await _checkpoint(session, request)
            if item is None:
                item = InteractionFinalization(
                    id=new_id("finalization"),
                    tenant_id=request.tenant_id,
                    interaction_id=request.interaction_id,
                    phase="streaming",
                    delivery_mode="render",
                    output_id=request.output_id or f"output_{request.interaction_id}",
                    terminal_status=terminal_status,
                    render_messages=_messages_data(messages),
                    candidate_deltas=[],
                    completion_data=completion_data,
                    expires_at=interaction.transcript_expires_at,
                )
                session.add(item)
                await session.flush()
            return _as_checkpoint(item)

    async def prepare_candidate(
        self,
        request: RuntimeRequest,
        content: str,
        deltas: tuple[str, ...],
        *,
        terminal_status: str,
        completion_data: dict[str, object],
    ) -> FinalizationCheckpoint:
        content, deltas = validate_candidate(content, deltas)
        async with self._database.session() as session:
            await self._database.set_tenant(session, request.tenant_id)
            interaction = await _interaction(session, request)
            item = await _checkpoint(session, request)
            if item is None:
                item = InteractionFinalization(
                    id=new_id("finalization"),
                    tenant_id=request.tenant_id,
                    interaction_id=request.interaction_id,
                    phase="prepared",
                    delivery_mode="candidate",
                    output_id=request.output_id or f"output_{request.interaction_id}",
                    terminal_status=terminal_status,
                    render_messages=[],
                    candidate_content=content,
                    candidate_deltas=list(deltas),
                    completion_data=completion_data,
                    expires_at=interaction.transcript_expires_at,
                )
                session.add(item)
                await session.flush()
            return _as_checkpoint(item)

    async def resume(self, request: RuntimeRequest) -> FinalizationCheckpoint | None:
        async with self._database.session() as session:
            await self._database.set_tenant(session, request.tenant_id)
            item = await _checkpoint(session, request)
            if item is None or item.phase == "completed":
                return None
            reset_output = item.phase == "streaming"
            if reset_output:
                if item.delivery_mode == "candidate":
                    item.phase = "prepared"
                item.attempt += 1
                await session.flush()
            return _as_checkpoint(item, reset_output=reset_output)

    async def mark_visible(self, request: RuntimeRequest) -> None:
        async with self._database.session() as session:
            await self._database.set_tenant(session, request.tenant_id)
            item = await _checkpoint(session, request)
            if item is not None and item.phase == "prepared":
                item.phase = "streaming"
                await session.flush()

    async def restart(
        self,
        request: RuntimeRequest,
        messages: tuple[ChatMessage, ...],
        *,
        reset_output: bool,
    ) -> FinalizationCheckpoint:
        async with self._database.session() as session:
            await self._database.set_tenant(session, request.tenant_id)
            item = await _checkpoint(session, request)
            if item is None or item.phase == "completed":
                raise ValueError("Finalization checkpoint is unavailable")
            item.render_messages = _messages_data(messages)
            item.phase = "streaming" if item.delivery_mode == "render" else "prepared"
            item.attempt += 1
            await session.flush()
            return _as_checkpoint(item, reset_output=reset_output)

    async def mark_completed(self, request: RuntimeRequest) -> None:
        async with self._database.session() as session:
            await self._database.set_tenant(session, request.tenant_id)
            item = await _checkpoint(session, request)
            if item is not None:
                item.phase = "completed"
                await session.flush()


async def _interaction(session: AsyncSession, request: RuntimeRequest) -> Interaction:
    item = await session.scalar(
        select(Interaction)
        .where(
            Interaction.tenant_id == request.tenant_id,
            Interaction.id == request.interaction_id,
        )
        .with_for_update()
    )
    if item is None:
        raise ValueError("Interaction is unavailable")
    return item


async def _checkpoint(
    session: AsyncSession, request: RuntimeRequest
) -> InteractionFinalization | None:
    return await session.scalar(
        select(InteractionFinalization)
        .where(
            InteractionFinalization.tenant_id == request.tenant_id,
            InteractionFinalization.interaction_id == request.interaction_id,
        )
        .with_for_update()
    )


def _as_checkpoint(
    item: InteractionFinalization, *, reset_output: bool = False
) -> FinalizationCheckpoint:
    delivery_mode = _delivery_mode(item.delivery_mode)
    content, deltas = _candidate_from_item(item, delivery_mode)
    return FinalizationCheckpoint(
        delivery_mode=delivery_mode,
        messages=_messages_from_data(item.render_messages),
        output_id=item.output_id,
        terminal_status=item.terminal_status,
        completion_data=dict(item.completion_data),
        candidate_content=content,
        candidate_deltas=deltas,
        reset_output=reset_output,
    )


def _delivery_mode(value: object) -> FinalizationDeliveryMode:
    if value in {"render", "candidate"}:
        return cast(FinalizationDeliveryMode, value)
    raise ValueError("Finalization checkpoint delivery mode is invalid")


def _candidate_from_item(
    item: InteractionFinalization, delivery_mode: FinalizationDeliveryMode
) -> tuple[str | None, tuple[str, ...]]:
    if delivery_mode == "render":
        return None, ()
    content = item.candidate_content
    if not isinstance(content, str):
        raise ValueError("Finalization candidate is invalid")
    return validate_candidate(content, tuple(_string_items(item.candidate_deltas)))


def _string_items(values: object) -> list[str]:
    if not isinstance(values, list):
        raise ValueError("Finalization candidate is invalid")
    items: list[str] = []
    for value in cast(list[object], values):
        if not isinstance(value, str):
            raise ValueError("Finalization candidate is invalid")
        items.append(value)
    return items


def _messages_data(messages: tuple[ChatMessage, ...]) -> list[dict[str, object]]:
    return [
        {
            "role": item.role,
            "content": item.content,
            "name": item.name,
            "tool_call_id": item.tool_call_id,
            "reasoning_content": item.reasoning_content,
            "tool_calls": [
                {"id": call.id, "name": call.name, "arguments": call.arguments}
                for call in item.tool_calls
            ],
        }
        for item in messages
    ]


def _messages_from_data(values: list[dict[str, object]]) -> tuple[ChatMessage, ...]:
    messages: list[ChatMessage] = []
    for value in values:
        role = value.get("role")
        content = value.get("content")
        if not isinstance(role, str) or (content is not None and not isinstance(content, str)):
            raise ValueError("Finalization checkpoint is invalid")
        calls = tuple(_tool_call(item) for item in _list(value.get("tool_calls")))
        messages.append(
            ChatMessage(
                role=role,
                content=content,
                name=_optional_string(value.get("name")),
                tool_call_id=_optional_string(value.get("tool_call_id")),
                tool_calls=calls,
                reasoning_content=_optional_string(value.get("reasoning_content")),
            )
        )
    return tuple(messages)


def _tool_call(value: object) -> ToolCall:
    if not isinstance(value, dict):
        raise ValueError("Finalization checkpoint tool call is invalid")
    call = cast(dict[str, object], value)
    call_id, name, arguments = call.get("id"), call.get("name"), call.get("arguments")
    if not isinstance(call_id, str) or not isinstance(name, str) or not isinstance(arguments, dict):
        raise ValueError("Finalization checkpoint tool call is invalid")
    return ToolCall(id=call_id, name=name, arguments=cast(dict[str, object], arguments))


def _list(value: object) -> list[object]:
    return cast(list[object], value) if isinstance(value, list) else []


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) else None
