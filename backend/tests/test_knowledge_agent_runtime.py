from __future__ import annotations

from dataclasses import replace

import pytest
from _agent_runtime_support import CapturingEvents, FakeModel, ask_user, profile, request

from app.modules.agent_runtime.contracts import ChatCompletion, ToolCall
from app.modules.agent_runtime.in_process import InProcessAgentRuntime
from app.modules.knowledge.runtime import KnowledgeEvidenceBundle, KnowledgeRuntimeContext


class _KnowledgeRuntime:
    def __init__(self, *, status: str = "ok") -> None:
        self.status = status
        self.contexts: list[KnowledgeRuntimeContext] = []

    async def retrieve(self, context: KnowledgeRuntimeContext) -> KnowledgeEvidenceBundle:
        self.contexts.append(context)
        return KnowledgeEvidenceBundle(
            content=(
                "<knowledge-evidence>\n[citation:chunk_test]\n"
                "Verified release policy.\n</knowledge-evidence>"
                if self.status == "ok"
                else ""
            ),
            citation_ids=(("chunk_test",) if self.status == "ok" else ()),
            status=self.status,
        )


@pytest.mark.asyncio
async def test_knowledge_agent_searches_evidence_in_the_shared_loop() -> None:
    evidence = _KnowledgeRuntime()
    model = FakeModel(
        [
            ChatCompletion(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="call_knowledge",
                        name="knowledge_search",
                        arguments={"query": "production release policy"},
                    ),
                ),
            ),
            ChatCompletion(content="The policy is verified [citation:chunk_test]."),
        ],
        auto_final_response=False,
    )
    runtime = InProcessAgentRuntime(
        model,
        max_tool_rounds=2,
        timeout_seconds=30,
        knowledge_runtime=evidence,
    )

    await runtime.execute(
        replace(request(), profile=replace(profile(), agent_type_key="knowledge")),
        CapturingEvents(),
    )

    assert len(model.calls) == 2
    assert evidence.contexts[0].query == "production release policy"
    assert any(
        "citation:chunk_test" in (message.content or "")
        for message in model.calls[1][0]
        if message.role == "tool"
    )
    assert all(
        "Knowledge Request Interpreter" not in (item.content or "") for item in model.calls[0][0]
    )


@pytest.mark.asyncio
async def test_knowledge_agent_reports_unavailable_retrieval_without_calling_it_no_results() -> (
    None
):
    evidence = _KnowledgeRuntime(status="unavailable")
    model = FakeModel(
        [
            ChatCompletion(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="call_knowledge",
                        name="knowledge_search",
                        arguments={"query": "production release policy"},
                    ),
                ),
            ),
            ChatCompletion(content="知识检索暂时不可用，当前无法核实该规则。"),
        ],
        auto_final_response=False,
    )
    events = CapturingEvents()
    runtime = InProcessAgentRuntime(
        model,
        max_tool_rounds=2,
        timeout_seconds=30,
        knowledge_runtime=evidence,
    )

    await runtime.execute(
        replace(request(), profile=replace(profile(), agent_type_key="knowledge")),
        events,
    )

    tool_result = next(
        message.content or "" for message in model.calls[1][0] if message.role == "tool"
    )
    assert "KNOWLEDGE_SEARCH_UNAVAILABLE" in tool_result
    assert events.items[-1][1]["content"] == "知识检索暂时不可用，当前无法核实该规则。"


@pytest.mark.asyncio
async def test_knowledge_root_loop_can_use_ask_user_as_a_waiting_terminal() -> None:
    model = FakeModel([ask_user("请提供入住城市和日期。")])
    events = CapturingEvents()
    runtime = InProcessAgentRuntime(model, max_tool_rounds=2, timeout_seconds=30)

    await runtime.execute(
        replace(
            request(),
            text="预定酒店",
            profile=replace(profile(), agent_type_key="knowledge"),
        ),
        events,
    )

    assert len(model.calls) == 1
    assert events.items[-1][0] == "ai.output.completed"
    assert events.items[-1][1]["runtime_status"] == "waiting_user_input"


@pytest.mark.asyncio
async def test_noninteractive_knowledge_loop_does_not_expose_ask_user() -> None:
    model = FakeModel(
        [ChatCompletion(content="当前入口不支持交互澄清。")], auto_final_response=False
    )
    runtime = InProcessAgentRuntime(model, max_tool_rounds=2, timeout_seconds=30)

    await runtime.execute(
        replace(
            request(),
            entry_type="schedule",
            profile=replace(profile(), agent_type_key="knowledge"),
        ),
        CapturingEvents(),
    )

    assert "ask_user" not in {tool.name for tool in model.calls[0][1]}
