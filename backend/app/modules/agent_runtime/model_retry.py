from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from app.core.agent_runtime import RuntimeLlmProfile
from app.modules.agent_runtime.contracts import (
    AgentModelPort,
    ChatCompletion,
    ChatCompletionDelta,
    ChatMessage,
    ModelProviderError,
    ModelToolChoice,
    ToolDefinition,
)
from app.modules.agent_runtime.diagnostics import RuntimeDiagnostics


async def complete_with_retry(
    model: AgentModelPort,
    llm: RuntimeLlmProfile,
    messages: tuple[ChatMessage, ...],
    tools: tuple[ToolDefinition, ...],
    *,
    max_retries: int,
    diagnostics: RuntimeDiagnostics | None = None,
    diagnostic_phase: str = "model_completion",
    tool_choice: ModelToolChoice | None = None,
) -> ChatCompletion:
    for attempt in range(max_retries + 1):
        try:
            if diagnostics is not None:
                await diagnostics.model_request(
                    diagnostic_phase,
                    llm,
                    messages,
                    tools,
                    attempt + 1,
                    tool_choice=tool_choice,
                )
            completion = await model.complete(
                llm,
                messages,
                tools,
                tool_choice=tool_choice,
            )
            if diagnostics is not None:
                await diagnostics.model_response(diagnostic_phase, completion)
            return completion
        except ModelProviderError as error:
            if not error.retryable or attempt >= max_retries:
                raise
            await asyncio.sleep(min(0.5, 0.1 * (attempt + 1)))
    raise AssertionError("model retry loop must either return or raise")


async def stream_with_retry(
    model: AgentModelPort,
    llm: RuntimeLlmProfile,
    messages: tuple[ChatMessage, ...],
    tools: tuple[ToolDefinition, ...],
    *,
    max_retries: int,
    diagnostics: RuntimeDiagnostics | None = None,
    diagnostic_phase: str = "agent_loop",
    tool_choice: ModelToolChoice | None = None,
) -> AsyncIterator[ChatCompletionDelta]:
    for attempt in range(max_retries + 1):
        received = False
        try:
            if diagnostics is not None:
                await diagnostics.model_request(
                    diagnostic_phase,
                    llm,
                    messages,
                    tools,
                    attempt + 1,
                    tool_choice=tool_choice,
                )
            async for delta in model.stream(llm, messages, tools, tool_choice=tool_choice):
                received = True
                yield delta
            return
        except ModelProviderError as error:
            if received or not error.retryable or attempt >= max_retries:
                raise
            await asyncio.sleep(min(0.5, 0.1 * (attempt + 1)))
    raise AssertionError("model stream retry loop must either return or raise")
