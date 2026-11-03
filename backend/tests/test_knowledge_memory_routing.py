from __future__ import annotations

from dataclasses import replace

import pytest
from _agent_runtime_support import (
    CapturingEvents,
    FakeConversationHistory,
    FakeMemoryRuntime,
    FakeModel,
    profile,
    request,
)

from app.modules.agent_runtime.contracts import ChatCompletion
from app.modules.agent_runtime.in_process import InProcessAgentRuntime
from app.modules.interactions.runtime import RuntimeControlState


class _SteeringReader:
    def __init__(self) -> None:
        self._message = "上海的"

    async def consume(self, runtime_request: object) -> RuntimeControlState:
        del runtime_request
        message, self._message = self._message, ""
        return RuntimeControlState(steering_messages=(message,) if message else ())


@pytest.mark.asyncio
async def test_knowledge_main_loop_receives_history_memory_and_latest_steering() -> None:
    model = FakeModel(
        [ChatCompletion(content="已结合上下文继续处理上海酒店预定。")],
        auto_final_response=False,
    )
    runtime = InProcessAgentRuntime(
        model,
        max_tool_rounds=2,
        timeout_seconds=30,
        memory_runtime=FakeMemoryRuntime("<memory-context>使用中文</memory-context>"),
        conversation_history=FakeConversationHistory(),
    )

    await runtime.execute(
        replace(
            request(),
            text="预定酒店",
            conversation_id="conversation_test",
            profile=replace(profile(), agent_type_key="knowledge"),
            resume_assistant_message="请问您想预定哪个城市的酒店？",
            control_reader=_SteeringReader(),
        ),
        CapturingEvents(),
    )

    messages = model.calls[0][0]
    assert any("使用中文" in (item.content or "") for item in messages)
    assert any("Earlier request" in (item.content or "") for item in messages)
    assert any("请问您想预定哪个城市" in (item.content or "") for item in messages)
    assert messages[-1].role == "user"
    assert messages[-1].content == "上海的"
