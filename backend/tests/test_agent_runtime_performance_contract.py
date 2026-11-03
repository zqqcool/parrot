from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field, replace
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
from _agent_runtime_support import (
    CapturingEvents,
    FakeModel,
    FakeSubagentDispatcher,
    profile,
    request,
)

from app.core.agent_runtime import RuntimeLlmProfile, RuntimeMcpServerProfile
from app.modules.agent_runtime.contracts import (
    AgentModelPort,
    ChatCompletion,
    ChatCompletionDelta,
    ChatMessage,
    ModelToolChoice,
    ToolCall,
    ToolDefinition,
)
from app.modules.agent_runtime.in_process import InProcessAgentRuntime
from app.modules.agent_runtime.mcp_executor import McpExecutor
from app.modules.interactions.history import ConversationHistoryPort, ConversationTurn
from app.modules.knowledge.runtime import KnowledgeEvidenceBundle
from app.modules.memory.runtime import MemoryRuntimePort


def _mcp_profile() -> RuntimeMcpServerProfile:
    return RuntimeMcpServerProfile(
        id="mcp_test",
        name="Test MCP",
        transport="streamable_http",
        endpoint="https://mcp.example.test/mcp",
        arguments=(),
        encrypted_credentials=(),
    )


def _unused_mcp_executor() -> tuple[McpExecutor, AsyncMock, AsyncMock]:
    discover = AsyncMock(return_value=())
    execute = AsyncMock(return_value={"status": "succeeded"})
    executor = cast(McpExecutor, SimpleNamespace(discover=discover, execute=execute))
    return executor, discover, execute


@dataclass
class _KnowledgeRuntime:
    calls: list[object] = field(default_factory=list[object])

    async def retrieve(self, context: object) -> KnowledgeEvidenceBundle:
        self.calls.append(context)
        return KnowledgeEvidenceBundle(content="Verified evidence.", status="ok")


@dataclass
class _ContextLoadGate:
    starts: int = 0
    ready: asyncio.Event = field(default_factory=asyncio.Event)

    async def arrive(self) -> None:
        self.starts += 1
        if self.starts == 2:
            self.ready.set()
        await asyncio.wait_for(self.ready.wait(), timeout=1)


@dataclass
class _GatedMemory:
    gate: _ContextLoadGate

    async def context_for(self, context: object) -> str:
        del context
        await self.gate.arrive()
        return ""

    async def handle(self, context: object, arguments: dict[str, object]) -> dict[str, object]:
        del context, arguments
        return {"status": "ok"}


@dataclass
class _GatedHistory:
    gate: _ContextLoadGate

    async def recent(
        self, context: object, *, turns: int, max_tokens: int
    ) -> tuple[ConversationTurn, ...]:
        del context, turns, max_tokens
        await self.gate.arrive()
        return ()


@pytest.mark.asyncio
async def test_direct_path_keeps_two_model_calls_and_skips_lazy_branches() -> None:
    model = FakeModel(
        [
            ChatCompletion(content='{"action":"direct_answer"}'),
            ChatCompletion(content="Direct answer."),
        ],
        auto_final_response=False,
    )
    mcp, discover, execute = _unused_mcp_executor()
    subagents = FakeSubagentDispatcher()
    runtime = InProcessAgentRuntime(
        model,
        max_tool_rounds=2,
        timeout_seconds=30,
        mcp_executor=mcp,
        subagent_dispatcher=subagents,
    )
    runtime_profile = replace(profile(), mcp_servers=(_mcp_profile(),))

    await runtime.execute(replace(request(), profile=runtime_profile), CapturingEvents())

    assert len(model.calls) == 2
    discover.assert_not_awaited()
    execute.assert_not_awaited()
    assert subagents.calls == []


@pytest.mark.asyncio
async def test_direct_path_loads_memory_and_history_concurrently() -> None:
    model = FakeModel(
        [
            ChatCompletion(content='{"action":"direct_answer"}'),
            ChatCompletion(content="Direct answer."),
        ],
        auto_final_response=False,
    )
    gate = _ContextLoadGate()
    runtime = InProcessAgentRuntime(
        model,
        max_tool_rounds=2,
        timeout_seconds=30,
        memory_runtime=cast(MemoryRuntimePort, _GatedMemory(gate)),
        conversation_history=cast(ConversationHistoryPort, _GatedHistory(gate)),
    )

    await runtime.execute(
        replace(request(), conversation_id="conversation_test"), CapturingEvents()
    )

    assert gate.starts == 2


@pytest.mark.asyncio
async def test_knowledge_tool_path_has_no_extra_analyzer_call_or_remote_discovery() -> None:
    model = FakeModel(
        [
            ChatCompletion(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="call_knowledge",
                        name="knowledge_search",
                        arguments={"query": "release policy"},
                    ),
                ),
            ),
            ChatCompletion(content="Knowledge answer."),
        ],
        auto_final_response=False,
    )
    evidence = _KnowledgeRuntime()
    mcp, discover, execute = _unused_mcp_executor()
    runtime = InProcessAgentRuntime(
        model,
        max_tool_rounds=2,
        timeout_seconds=30,
        knowledge_runtime=evidence,
        mcp_executor=mcp,
    )
    runtime_profile = replace(profile(), agent_type_key="knowledge", mcp_servers=(_mcp_profile(),))

    await runtime.execute(replace(request(), profile=runtime_profile), CapturingEvents())

    assert len(model.calls) == 2
    assert "knowledge_search" in {tool.name for tool in model.calls[0][1]}
    assert len(evidence.calls) == 1
    discover.assert_not_awaited()
    execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_single_tool_path_has_one_planner_and_two_agent_turns() -> None:
    model = FakeModel(
        [
            ChatCompletion(content='{"action":"capability_lookup"}'),
            ChatCompletion(
                content=None,
                tool_calls=(ToolCall(id="call_time", name="time", arguments={"action": "now"}),),
                reasoning_content="private tool reasoning",
            ),
            ChatCompletion(content="The current time is available."),
        ],
        auto_final_response=False,
    )
    runtime = InProcessAgentRuntime(model, max_tool_rounds=2, timeout_seconds=30)
    events = CapturingEvents()

    await runtime.execute(request(), events)

    assert len(model.calls) == 3
    assert [event_type for event_type, _ in events.items].count("ai.tool.started") == 1
    assert [event_type for event_type, _ in events.items].count("ai.tool.completed") == 1
    assert model.calls[2][0][-2].reasoning_content == "private tool reasoning"
    assert all(
        "private tool reasoning" not in str(data)
        for event_type, data in events.items
        if event_type.startswith("ai.output.")
    )


@pytest.mark.asyncio
async def test_entry_subagent_dispatch_stops_after_the_planner_call() -> None:
    user_text = "Research release notes and verify deployment status."
    first_quote = "Research release notes"
    second_quote = "verify deployment status"
    model = FakeModel(
        [
            ChatCompletion(
                content=(
                    '{"action":"subagent_dispatch","tasks":['
                    '{"id":"research","objective":"Research release notes",'
                    '"source_role":"latest_user_request",'
                    f'"source_quote":"{first_quote}","source_span":{{"start":0,'
                    f'"end":{len(first_quote)}}}}},'
                    '{"id":"verify","objective":"Verify deployment status",'
                    '"source_role":"latest_user_request",'
                    f'"source_quote":"{second_quote}","source_span":{{"start":'
                    f'{user_text.index(second_quote)},"end":'
                    f"{user_text.index(second_quote) + len(second_quote)}}}}}]}}"
                )
            )
        ],
        auto_final_response=False,
    )
    subagents = FakeSubagentDispatcher()
    runtime = InProcessAgentRuntime(
        model,
        max_tool_rounds=2,
        timeout_seconds=30,
        subagent_dispatcher=subagents,
    )

    await runtime.execute(replace(request(), text=user_text), CapturingEvents())

    assert len(model.calls) == 1
    assert len(subagents.calls) == 1


class _GatedDirectModel(AgentModelPort):
    def __init__(self) -> None:
        self.first_delta = asyncio.Event()
        self.release_tail = asyncio.Event()
        self.calls = 0

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
        del llm, messages, tools, tool_choice
        self.calls += 1
        return ChatCompletion(content='{"action":"direct_answer"}')

    async def stream(
        self,
        llm: RuntimeLlmProfile,
        messages: tuple[ChatMessage, ...],
        tools: tuple[ToolDefinition, ...] = (),
        *,
        tool_choice: ModelToolChoice | None = None,
    ) -> AsyncIterator[ChatCompletionDelta]:
        del llm, messages, tools, tool_choice
        self.calls += 1
        yield ChatCompletionDelta(content_delta="First")
        self.first_delta.set()
        await self.release_tail.wait()
        yield ChatCompletionDelta(content_delta=" second")


@pytest.mark.asyncio
async def test_direct_path_publishes_the_first_provider_delta_immediately() -> None:
    model = _GatedDirectModel()
    events = CapturingEvents()
    runtime = InProcessAgentRuntime(model, max_tool_rounds=2, timeout_seconds=30)

    execution = asyncio.create_task(runtime.execute(request(), events))
    await asyncio.wait_for(model.first_delta.wait(), timeout=1)

    assert [item for item in events.items if item[0] == "ai.output.delta"] == [
        (
            "ai.output.delta",
            {"output_id": "output_interaction_test", "delta": "First", "delta_index": 0},
        )
    ]

    model.release_tail.set()
    await asyncio.wait_for(execution, timeout=1)
    assert model.calls == 2
    assert [event_type for event_type, _ in events.items][-2:] == [
        "ai.output.delta",
        "ai.output.completed",
    ]
