from __future__ import annotations

import json

from app.modules.agent_runtime.contracts import ChatMessage, ModelToolChoice, ToolDefinition

SNAPSHOT_FORMAT = "openai-compatible.chat-completions.v1"


def provider_request_snapshot(
    messages: tuple[ChatMessage, ...],
    tools: tuple[ToolDefinition, ...],
    *,
    tool_choice: ModelToolChoice | None = None,
) -> dict[str, object]:
    """Return the provider-ready prompt fields without model configuration or credentials."""
    snapshot: dict[str, object] = {
        "format": SNAPSHOT_FORMAT,
        "messages": [message_payload(message) for message in messages],
        "tools": [tool_definition_payload(tool) for tool in tools],
    }
    if tool_choice is not None:
        snapshot["tool_choice"] = tool_choice
    return snapshot


def message_payload(message: ChatMessage) -> dict[str, object]:
    payload: dict[str, object] = {"role": message.role, "content": message.content}
    if message.name is not None:
        payload["name"] = message.name
    if message.tool_call_id is not None:
        payload["tool_call_id"] = message.tool_call_id
    if message.tool_calls:
        payload["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": json.dumps(call.arguments)},
            }
            for call in message.tool_calls
        ]
    if message.reasoning_content is not None:
        payload["reasoning_content"] = message.reasoning_content
    return payload


def tool_payload(tool: ToolDefinition) -> dict[str, object]:
    return {
        "name": tool.name,
        "description": tool.description,
        "parameters": tool.argument_schema(),
    }


def tool_definition_payload(tool: ToolDefinition) -> dict[str, object]:
    return {"type": "function", "function": tool_payload(tool)}
