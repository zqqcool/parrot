from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path

from app.core.agent_runtime import AgentRuntimeProfile, RuntimeLlmProfile, RuntimeSkillProfile
from app.infrastructure.credential_cipher import CredentialCipher, llm_credential_context
from app.modules.agent_runtime.contracts import (
    AgentModelPort,
    ChatCompletion,
    ChatCompletionDelta,
    ChatMessage,
    ModelToolChoice,
    ToolCall,
    ToolCallDelta,
    ToolDefinition,
)
from app.modules.interactions.history import ConversationHistoryMessage, ConversationTurn
from app.modules.interactions.runtime import RuntimeControlState, RuntimeEventSink, RuntimeRequest
from app.modules.memory.context import MemoryContextItem, MemoryRecallContext
from app.modules.memory.runtime import MemoryRuntimeContext
from app.modules.schedules.runtime import ScheduleRuntimeContext

EventItem = tuple[str, dict[str, object]]
TraceItem = tuple[str, dict[str, object]]
ModelCall = tuple[tuple[ChatMessage, ...], tuple[ToolDefinition, ...]]
ROOT = Path(__file__).resolve().parents[1]
TEST_CREDENTIAL_KEY = "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA"


def credential_cipher() -> CredentialCipher:
    return CredentialCipher(TEST_CREDENTIAL_KEY)


TEST_LLM_CREDENTIAL_ENVELOPE = credential_cipher().encrypt(
    "secret", context=llm_credential_context("llm_test")
)


def _event_items() -> list[EventItem]:
    return []


def _trace_items() -> list[TraceItem]:
    return []


def _model_calls() -> list[ModelCall]:
    return []


def _tool_choices() -> list[ModelToolChoice | None]:
    return []


def _rendered_answers() -> list[str]:
    return []


def _memory_contexts() -> list[MemoryRuntimeContext]:
    return []


def _memory_calls() -> list[dict[str, object]]:
    return []


def _resume_message_batches() -> list[tuple[ChatMessage, ...]]:
    return []


def _source_names() -> list[str]:
    return []


def _optional_call_ids() -> list[str | None]:
    return []


def _schedule_contexts() -> list[ScheduleRuntimeContext]:
    return []


def _history_contexts() -> list[object]:
    return []


@dataclass
class CapturingEvents(RuntimeEventSink):
    items: list[EventItem] = field(default_factory=_event_items)
    traces: list[TraceItem] = field(default_factory=_trace_items)
    completed: asyncio.Event = field(default_factory=asyncio.Event)

    async def append(
        self,
        *,
        tenant_id: str,
        interaction_id: str,
        request_id: str,
        event_type: str,
        data: dict[str, object],
        terminal_status: str | None = None,
        runtime_event_sequence: int | None = None,
        lease_owner: str | None = None,
    ) -> object:
        del (
            tenant_id,
            interaction_id,
            request_id,
            terminal_status,
            runtime_event_sequence,
            lease_owner,
        )
        self.items.append((event_type, data))
        if event_type == "ai.output.completed":
            self.completed.set()
        return object()

    async def record_trace(
        self,
        *,
        tenant_id: str,
        interaction_id: str,
        trace_type: str,
        data: dict[str, object],
        lease_owner: str | None = None,
    ) -> object:
        del tenant_id, interaction_id, lease_owner
        self.traces.append((trace_type, data))
        return object()


@dataclass
class FakeModel(AgentModelPort):
    responses: list[ChatCompletion]
    calls: list[ModelCall] = field(default_factory=_model_calls)
    tool_choices: list[ModelToolChoice | None] = field(default_factory=_tool_choices)
    auto_final_response: bool = True
    rendered_answers: list[str] = field(default_factory=_rendered_answers)
    last_plain_content: str | None = None

    def validate(self, llm: RuntimeLlmProfile) -> None:
        del llm

    async def complete(
        self,
        llm: RuntimeLlmProfile,
        messages: tuple[ChatMessage, ...],
        tools: tuple[ToolDefinition, ...] = (),
        *,
        tool_choice: ModelToolChoice | None = None,
    ) -> ChatCompletion:
        del llm
        self.calls.append((messages, tools))
        self.tool_choices.append(tool_choice)
        completion = self.responses.pop(0)
        if completion.content and not completion.tool_calls:
            self.last_plain_content = completion.content
        for call in completion.tool_calls:
            if call.name != "final_response":
                continue
            content = call.arguments.get("content")
            if isinstance(content, str) and content.strip():
                self.last_plain_content = content.strip()
        return completion

    async def stream(
        self,
        llm: RuntimeLlmProfile,
        messages: tuple[ChatMessage, ...],
        tools: tuple[ToolDefinition, ...] = (),
        *,
        tool_choice: ModelToolChoice | None = None,
    ) -> AsyncIterator[ChatCompletionDelta]:
        if not tools and self.rendered_answers:
            self.calls.append((messages, tools))
            self.tool_choices.append(tool_choice)
            completion = ChatCompletion(content=self.rendered_answers.pop(0))
        elif not tools and not self.responses and self.last_plain_content:
            self.calls.append((messages, tools))
            self.tool_choices.append(tool_choice)
            completion = ChatCompletion(content=self.last_plain_content)
        else:
            completion = await self.complete(
                llm,
                messages,
                tools,
                tool_choice=tool_choice,
            )
        if self.auto_final_response and _offers_final_response(tools) and completion.content:
            self.rendered_answers.append(completion.content)
            completion = final_response()
        if completion.reasoning_content:
            yield ChatCompletionDelta(reasoning_content_delta=completion.reasoning_content)
        if completion.content:
            yield ChatCompletionDelta(content_delta=completion.content)
        for index, call in enumerate(completion.tool_calls):
            yield ChatCompletionDelta(
                tool_call_deltas=(
                    ToolCallDelta(
                        index=index,
                        id=call.id,
                        name=call.name,
                        arguments_delta=json.dumps(call.arguments),
                    ),
                )
            )


def final_response() -> ChatCompletion:
    return ChatCompletion(
        content=None,
        tool_calls=(
            ToolCall(
                id="call_final_response",
                name="final_response",
                arguments={},
            ),
        ),
    )


def ask_user(question: str) -> ChatCompletion:
    return ChatCompletion(
        content=None,
        tool_calls=(
            ToolCall(
                id="call_ask_user",
                name="ask_user",
                arguments={"question": question},
            ),
        ),
    )


def _offers_final_response(tools: tuple[ToolDefinition, ...]) -> bool:
    return any(tool.name == "final_response" for tool in tools)


class CancelReader:
    async def consume(self, request: RuntimeRequest) -> RuntimeControlState:
        del request
        return RuntimeControlState(cancel_requested=True)


@dataclass
class FakeMemoryRuntime:
    context: str
    contexts: list[MemoryRuntimeContext] = field(default_factory=_memory_contexts)
    calls: list[dict[str, object]] = field(default_factory=_memory_calls)

    async def context_for(self, context: MemoryRuntimeContext) -> str:
        self.contexts.append(context)
        return self.context

    async def pinned_for(self, context: MemoryRuntimeContext) -> tuple[MemoryContextItem, ...]:
        self.contexts.append(context)
        if not self.context:
            return ()
        content = self.context.replace("<memory-context>", "").replace("</memory-context>", "")
        return (
            MemoryContextItem(
                id="memory_test",
                scope_type="user",
                key="test_context",
                memory_type="user_preference",
                content=content,
                occurred_at=None,
            ),
        )

    async def recall_for(self, context: MemoryRuntimeContext, query: str) -> MemoryRecallContext:
        del query
        self.contexts.append(context)
        return MemoryRecallContext()

    async def handle(
        self, context: MemoryRuntimeContext, arguments: dict[str, object]
    ) -> dict[str, object]:
        self.contexts.append(context)
        self.calls.append(arguments)
        return {"status": "ok", "items": []}


@dataclass
class FakeSubagentDispatcher:
    calls: list[dict[str, object]] = field(default_factory=_memory_calls)
    resume_messages: list[tuple[ChatMessage, ...]] = field(default_factory=_resume_message_batches)
    sources: list[str] = field(default_factory=_source_names)
    dispatch_call_ids: list[str | None] = field(default_factory=_optional_call_ids)

    async def dispatch(
        self,
        request: RuntimeRequest,
        arguments: dict[str, object],
        events: RuntimeEventSink,
        *,
        resume_messages: list[ChatMessage] | None = None,
        source: str = "functional_planner",
        dispatch_call_id: str | None = None,
    ) -> dict[str, object]:
        del request, events
        self.calls.append(arguments)
        self.resume_messages.append(tuple(resume_messages or ()))
        self.sources.append(source)
        self.dispatch_call_ids.append(dispatch_call_id)
        return {"status": "waiting_subagents", "board_id": "board_test"}

    async def settle_child(self, request: RuntimeRequest, events: RuntimeEventSink) -> None:
        del request, events


@dataclass
class FakeScheduleRuntime:
    contexts: list[ScheduleRuntimeContext] = field(default_factory=_schedule_contexts)
    calls: list[dict[str, object]] = field(default_factory=_memory_calls)

    async def handle(
        self, context: ScheduleRuntimeContext, arguments: dict[str, object]
    ) -> dict[str, object]:
        self.contexts.append(context)
        self.calls.append(arguments)
        return {"status": "ok", "schedule": {"id": "schedule_test"}}


@dataclass
class FakeConversationHistory:
    contexts: list[object] = field(default_factory=_history_contexts)

    async def recent(
        self, context: object, *, turns: int, max_tokens: int
    ) -> tuple[ConversationTurn, ...]:
        del turns, max_tokens
        self.contexts.append(context)
        return (
            ConversationTurn(
                interaction_id="interaction_earlier",
                user_content="Earlier request",
                assistant_content="Earlier answer",
            ),
        )

    async def resume_messages(
        self, context: object, *, through_sequence: int, max_tokens: int
    ) -> tuple[ConversationHistoryMessage, ...]:
        del context, through_sequence, max_tokens
        return ()


def profile() -> AgentRuntimeProfile:
    return AgentRuntimeProfile(
        llm=RuntimeLlmProfile(
            id="llm_test",
            provider="openai",
            model="test-model",
            base_url="https://api.example.test/v1",
            credential_envelope=TEST_LLM_CREDENTIAL_ENVELOPE,
        ),
        skills=(
            RuntimeSkillProfile(
                id="skill_test",
                name="release-notes",
                description="Summarize release notes",
                instructions="Produce concise release notes from supplied data.",
                manifest={},
                version=1,
            ),
        ),
    )


def request() -> RuntimeRequest:
    return RuntimeRequest(
        interaction_id="interaction_test",
        tenant_id="tenant_test",
        runtime_agent_id="runtime_agent_test",
        agent_id="agent_test",
        actor_type="anonymous",
        actor_id="visitor_test",
        entry_type="websocket",
        input_type="text",
        text="Prepare release notes",
        request_id="request_test",
        profile=profile(),
    )
