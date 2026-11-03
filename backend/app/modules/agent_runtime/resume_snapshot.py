from __future__ import annotations

import json
from typing import cast

from app.modules.agent_runtime.contracts import ChatMessage, ToolCall

MAX_RESUME_SNAPSHOT_BYTES = 64 * 1024


class ResumeSnapshotTooLarge(ValueError):
    """The root loop cannot be resumed safely within the bounded payload."""


def create_resume_snapshot(
    messages: list[ChatMessage],
    *,
    max_bytes: int = MAX_RESUME_SNAPSHOT_BYTES,
    exclude_tool_call_id: str | None = None,
) -> tuple[dict[str, object], ...]:
    stable_messages = _without_active_dispatch(messages, exclude_tool_call_id)
    snapshot = tuple(_serialize_message(message) for message in stable_messages)
    encoded = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).encode()
    if len(encoded) > max_bytes:
        raise ResumeSnapshotTooLarge("subagent resume context exceeds 64 KiB")
    return snapshot


def restore_resume_snapshot(value: tuple[dict[str, object], ...]) -> list[ChatMessage]:
    restored: list[ChatMessage] = []
    for raw in value:
        role = raw.get("role")
        if role not in {"system", "user", "assistant", "tool"}:
            raise ValueError("subagent resume message role is invalid")
        restored.append(
            ChatMessage(
                role=cast(str, role),
                content=_optional_text(raw.get("content")),
                name=_optional_text(raw.get("name")),
                tool_call_id=_optional_text(raw.get("tool_call_id")),
                tool_calls=_restore_tool_calls(raw.get("tool_calls")),
            )
        )
    return restored


def _without_active_dispatch(
    messages: list[ChatMessage], exclude_tool_call_id: str | None
) -> list[ChatMessage]:
    if messages and any(
        call.id == exclude_tool_call_id
        if exclude_tool_call_id is not None
        else call.name == "subagent_dispatch"
        for call in messages[-1].tool_calls
    ):
        return messages[:-1]
    return messages


def _serialize_message(message: ChatMessage) -> dict[str, object]:
    value: dict[str, object] = {"role": message.role, "content": message.content}
    if message.name:
        value["name"] = message.name
    if message.tool_call_id:
        value["tool_call_id"] = message.tool_call_id
    if message.tool_calls:
        value["tool_calls"] = [
            {
                "id": call.id,
                "name": call.name,
                "arguments": call.arguments,
            }
            for call in message.tool_calls
        ]
    return value


def _restore_tool_calls(value: object) -> tuple[ToolCall, ...]:
    if not isinstance(value, list):
        return ()
    calls: list[ToolCall] = []
    for raw in cast(list[object], value):
        if not isinstance(raw, dict):
            raise ValueError("subagent resume tool call is invalid")
        item = cast(dict[str, object], raw)
        call_id, name, arguments = item.get("id"), item.get("name"), item.get("arguments")
        if (
            not isinstance(call_id, str)
            or not isinstance(name, str)
            or not isinstance(arguments, dict)
        ):
            raise ValueError("subagent resume tool call is invalid")
        calls.append(
            ToolCall(
                id=call_id,
                name=name,
                arguments=cast(dict[str, object], arguments),
            )
        )
    return tuple(calls)


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) else None
