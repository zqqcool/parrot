from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import cast

from app.core.agent_runtime import RuntimeLlmProfile
from app.modules.agent_runtime.contracts import (
    AgentModelPort,
    ChatCompletion,
    ChatCompletionDelta,
    ChatMessage,
    ModelProviderError,
    ModelTokenUsage,
    ModelToolChoice,
    ToolCall,
    ToolCallDelta,
    ToolDefinition,
)
from app.modules.agent_runtime.diagnostics import RuntimeDiagnostics
from app.modules.agent_runtime.live_stream import LiveTurnPublisher
from app.modules.agent_runtime.model_retry import stream_with_retry


def _string_parts() -> list[str]:
    return []


@dataclass
class _ToolCallBuffer:
    id: str | None = None
    name: str | None = None
    arguments: list[str] = field(default_factory=_string_parts)

    def append(self, delta: ToolCallDelta) -> None:
        self.id = delta.id or self.id
        self.name = delta.name or self.name
        if delta.arguments_delta:
            self.arguments.append(delta.arguments_delta)

    def build(self) -> ToolCall:
        if self.id is None or self.name is None:
            raise ModelProviderError("Model provider stream tool call is incomplete")
        try:
            raw = cast(object, json.loads("".join(self.arguments)))
        except json.JSONDecodeError as error:
            raise ModelProviderError("Model provider stream tool call is invalid") from error
        if not isinstance(raw, dict):
            raise ModelProviderError("Model provider stream tool call is invalid")
        values = cast(dict[object, object], raw)
        if not all(isinstance(key, str) for key in values):
            raise ModelProviderError("Model provider stream tool call is invalid")
        return ToolCall(
            id=self.id,
            name=self.name,
            arguments={cast(str, key): value for key, value in values.items()},
        )


async def stream_completion(
    model: AgentModelPort,
    llm: RuntimeLlmProfile,
    messages: tuple[ChatMessage, ...],
    tools: tuple[ToolDefinition, ...],
    diagnostics: RuntimeDiagnostics | None = None,
    *,
    max_retries: int,
    tool_choice: ModelToolChoice | None = None,
    live: LiveTurnPublisher | None = None,
) -> ChatCompletion:
    turn = 0
    started_at = 0.0
    if diagnostics is not None:
        turn, started_at = diagnostics.begin_model_turn()
    content: list[str] = []
    reasoning: list[str] = []
    calls: dict[int, _ToolCallBuffer] = {}
    finish_reason: str | None = None
    usage: ModelTokenUsage | None = None
    first_content_recorded = False
    async for delta in stream_with_retry(
        model,
        llm,
        messages,
        tools,
        max_retries=max_retries,
        diagnostics=diagnostics,
        diagnostic_phase="agent_loop",
        tool_choice=tool_choice,
    ):
        first_content_recorded = await _consume_stream_delta(
            delta,
            content=content,
            reasoning=reasoning,
            calls=calls,
            live=live,
            diagnostics=diagnostics,
            first_content_recorded=first_content_recorded,
        )
        if delta.finish_reason is not None:
            finish_reason = delta.finish_reason
        if delta.usage is not None:
            usage = delta.usage
    tool_calls = tuple(item.build() for _, item in sorted(calls.items()))
    completion = ChatCompletion(
        content="".join(content) or None,
        tool_calls=tool_calls,
        content_deltas=tuple(content),
        finish_reason=finish_reason,
        reasoning_content="".join(reasoning) or None,
        reasoning_deltas=tuple(reasoning),
        usage=usage,
    )
    if diagnostics is not None:
        await diagnostics.model_response("agent_loop", completion)
        await diagnostics.model_turn_completed(
            "agent_loop",
            turn=turn,
            started_at=started_at,
            tool_call_count=len(tool_calls),
            content_characters=len(completion.content or ""),
        )
    return completion


async def _consume_stream_delta(
    delta: ChatCompletionDelta,
    *,
    content: list[str],
    reasoning: list[str],
    calls: dict[int, _ToolCallBuffer],
    live: LiveTurnPublisher | None,
    diagnostics: RuntimeDiagnostics | None,
    first_content_recorded: bool,
) -> bool:
    if delta.tool_call_deltas:
        for tool_delta in delta.tool_call_deltas:
            calls.setdefault(tool_delta.index, _ToolCallBuffer()).append(tool_delta)
        if live is not None:
            await live.on_tool_call_delta()
    if delta.content_delta:
        content.append(delta.content_delta)
        if diagnostics is not None and not first_content_recorded:
            first_content_recorded = True
            await diagnostics.milestone(
                "provider_first_content_delta",
                phase="agent_loop",
            )
        if live is not None:
            await live.on_content_delta(delta.content_delta)
    if delta.reasoning_content_delta:
        reasoning.append(delta.reasoning_content_delta)
        if live is not None:
            await live.on_reasoning_delta(delta.reasoning_content_delta)
    return first_content_recorded
