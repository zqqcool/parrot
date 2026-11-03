from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal, Protocol

from app.core.agent_runtime import RuntimeLlmProfile
from app.modules.agent_runtime.tool_schema import JsonSchema

ModelToolChoice = Literal["auto", "none", "required"]


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, object]


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str | None
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()
    reasoning_content: str | None = None


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    parameters: JsonSchema

    def __post_init__(self) -> None:
        schema = self.parameters.to_dict()
        if schema.get("type") != "object" or schema.get("additionalProperties") is not False:
            raise TypeError("tool parameters must be a closed root object schema")
        self.parameters.validate_schema()

    def argument_schema(self) -> dict[str, object]:
        """JSON Schema used for provider payloads and argument validation."""
        return self.parameters.to_dict()

    def accepts_arguments(self, arguments: dict[str, object]) -> bool:
        return self.parameters.matches(arguments)


@dataclass(frozen=True)
class ModelTokenUsage:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    cached_tokens: int | None = None


@dataclass(frozen=True)
class ChatCompletion:
    content: str | None
    tool_calls: tuple[ToolCall, ...] = ()
    content_deltas: tuple[str, ...] = ()
    finish_reason: str | None = None
    reasoning_content: str | None = None
    reasoning_deltas: tuple[str, ...] = ()
    usage: ModelTokenUsage | None = None


@dataclass(frozen=True)
class ToolCallDelta:
    index: int
    id: str | None = None
    name: str | None = None
    arguments_delta: str = ""


@dataclass(frozen=True)
class ChatCompletionDelta:
    content_delta: str = ""
    tool_call_deltas: tuple[ToolCallDelta, ...] = ()
    finish_reason: str | None = None
    reasoning_content_delta: str = ""
    usage: ModelTokenUsage | None = None


class ModelProviderError(RuntimeError):
    """A stable error boundary for a configured model provider."""

    def __init__(
        self,
        message: str,
        *,
        retryable: bool = False,
        tool_choice_rejected: bool = False,
    ) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.tool_choice_rejected = tool_choice_rejected


class AgentModelPort(Protocol):
    def validate(self, llm: RuntimeLlmProfile) -> None: ...

    async def complete(
        self,
        llm: RuntimeLlmProfile,
        messages: tuple[ChatMessage, ...],
        tools: tuple[ToolDefinition, ...] = (),
        *,
        tool_choice: ModelToolChoice | None = None,
    ) -> ChatCompletion: ...

    def stream(
        self,
        llm: RuntimeLlmProfile,
        messages: tuple[ChatMessage, ...],
        tools: tuple[ToolDefinition, ...] = (),
        *,
        tool_choice: ModelToolChoice | None = None,
    ) -> AsyncIterator[ChatCompletionDelta]: ...
