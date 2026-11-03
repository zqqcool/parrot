from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast

import pytest
from _agent_runtime_support import credential_cipher

from app.core.agent_runtime import (
    AgentRuntimeProfile,
    RuntimeLlmProfile,
    RuntimeSkillProfile,
    profile_to_payload,
)
from app.core.config import AppConfig
from app.core.task_dispatch import TaskDispatcher
from app.infrastructure.credential_cipher import llm_credential_context
from app.infrastructure.db.session import DatabaseManager
from app.modules.agent_runtime.contracts import (
    ChatCompletion,
    ChatCompletionDelta,
    ChatMessage,
    ModelProviderError,
    ModelToolChoice,
    ToolCallDelta,
    ToolDefinition,
)
from app.modules.agent_runtime.durable import (
    ClaimedInteraction,
    DurableInProcessRuntime,
    ResumeContext,
    RuntimeWorker,
)
from app.modules.agent_runtime.in_process import InProcessAgentRuntime
from app.modules.interactions.runtime import (
    RuntimeActiveSkill,
    RuntimeControlRequest,
    RuntimeEventSink,
    RuntimeRequest,
    RuntimeSkillContext,
)

TEST_CREDENTIAL_ENVELOPE = credential_cipher().encrypt(
    "secret", context=llm_credential_context("llm_test")
)


class RecordingEvents:
    def __init__(self) -> None:
        self.items: list[dict[str, object]] = []

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
        self.items.append(
            {
                "tenant_id": tenant_id,
                "interaction_id": interaction_id,
                "request_id": request_id,
                "event_type": event_type,
                "data": data,
                "terminal_status": terminal_status,
                "runtime_event_sequence": runtime_event_sequence,
                "lease_owner": lease_owner,
            }
        )
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
        del tenant_id, interaction_id, trace_type, data, lease_owner
        return object()


class RecordingTaskDispatcher:
    def __init__(self) -> None:
        self.runtime_calls: list[tuple[str, str]] = []

    async def dispatch_runtime(self, tenant_id: str, interaction_id: str) -> None:
        self.runtime_calls.append((tenant_id, interaction_id))


class RecordingModel:
    def __init__(self, *, fail_validation: bool = False) -> None:
        self.fail_validation = fail_validation
        self.validated: list[RuntimeLlmProfile] = []

    def validate(self, llm: RuntimeLlmProfile) -> None:
        self.validated.append(llm)
        if self.fail_validation:
            raise ModelProviderError("invalid")

    async def complete(
        self,
        llm: RuntimeLlmProfile,
        messages: tuple[ChatMessage, ...],
        tools: tuple[ToolDefinition, ...] = (),
        *,
        tool_choice: ModelToolChoice | None = None,
    ) -> ChatCompletion:
        del llm, messages, tools, tool_choice
        return ChatCompletion(content='{"action":"direct_answer"}')

    async def stream(
        self,
        llm: RuntimeLlmProfile,
        messages: tuple[ChatMessage, ...],
        tools: tuple[ToolDefinition, ...] = (),
        *,
        tool_choice: ModelToolChoice | None = None,
    ) -> AsyncIterator[ChatCompletionDelta]:
        del llm, messages, tool_choice
        if any(tool.name == "final_response" for tool in tools):
            yield ChatCompletionDelta(
                tool_call_deltas=(
                    ToolCallDelta(
                        index=0,
                        id="final_response",
                        name="final_response",
                        arguments_delta=json.dumps({}),
                    ),
                )
            )
            return
        yield ChatCompletionDelta(content_delta="completed")


@pytest.mark.asyncio
async def test_durable_port_prepares_then_dispatches_work_without_resolving_credentials() -> None:
    dispatcher = RecordingTaskDispatcher()
    runtime = DurableInProcessRuntime(cast(TaskDispatcher, dispatcher))

    request = _request()
    result = await runtime.prepare(request)
    await runtime.dispatch(request)

    assert result.status == "accepted"
    assert result.execution_id == "runtime:interaction_test"
    assert result.recovery_lease_seconds is None
    assert dispatcher.runtime_calls == [("tenant_test", "interaction_test")]


@pytest.mark.asyncio
async def test_durable_port_persists_cancel_and_steering_requests() -> None:
    dispatcher = RecordingTaskDispatcher()
    runtime = DurableInProcessRuntime(cast(TaskDispatcher, dispatcher))
    events = RecordingEvents()
    control = RuntimeControlRequest(
        interaction_id="interaction_test",
        tenant_id="tenant_test",
        actor_type="anonymous",
        actor_id="visitor_test",
        execution_id="runtime:interaction_test",
        request_id="req_test",
        message="Use a shorter answer",
    )

    await runtime.cancel(control, events)
    await runtime.steer(control, events)

    assert [item["event_type"] for item in events.items] == [
        "ai.interaction.cancel.requested",
        "ai.interaction.steer.requested",
    ]
    assert events.items[0]["terminal_status"] is None
    assert cast(dict[str, object], events.items[1]["data"])["message"] == "Use a shorter answer"
    assert dispatcher.runtime_calls == []


@pytest.mark.asyncio
async def test_durable_port_requeues_a_waiting_interaction_when_steered() -> None:
    dispatcher = RecordingTaskDispatcher()
    runtime = DurableInProcessRuntime(cast(TaskDispatcher, dispatcher))
    events = RecordingEvents()
    control = RuntimeControlRequest(
        interaction_id="interaction_test",
        tenant_id="tenant_test",
        actor_type="anonymous",
        actor_id="visitor_test",
        execution_id="runtime:interaction_test",
        request_id="req_test",
        message="Use the production release.",
        resume_from_waiting=True,
    )

    await runtime.steer(control, events)

    assert events.items == [
        {
            "tenant_id": "tenant_test",
            "interaction_id": "interaction_test",
            "request_id": "req_test",
            "event_type": "ai.interaction.steer.requested",
            "data": {
                "message": "Use the production release.",
                "runtime_execution_id": "runtime:interaction_test",
            },
            "terminal_status": "accepted",
            "runtime_event_sequence": None,
            "lease_owner": None,
        }
    ]
    assert dispatcher.runtime_calls == [("tenant_test", "interaction_test")]


@pytest.mark.asyncio
async def test_worker_replays_persisted_input_and_profile_snapshot() -> None:
    executor = RecordingExecutor()
    worker = _TestRuntimeWorker(
        cast(
            AppConfig,
            SimpleNamespace(
                runtime=SimpleNamespace(request_timeout_seconds=30, lease_heartbeat_seconds=15)
            ),
        ),
        executor,
        database=cast(DatabaseManager, SimpleNamespace()),
        notifier=NullNotifier(),
    )
    events = RecordingEvents()
    worker.events = events
    claim = _claim()

    await worker.process_claim(claim)

    assert executor.request is not None
    assert executor.request.text == "Summarize the report"
    assert executor.request.profile == _profile()
    assert executor.request.output_id is not None
    assert events.items[0]["event_type"] == "ai.interaction.status"
    assert events.items[0]["data"] == {
        "status": "running",
        "runtime_execution_id": "runtime:interaction_test",
    }


@pytest.mark.asyncio
async def test_worker_restores_the_legacy_active_skill_checkpoint() -> None:
    executor = RecordingExecutor()
    worker = _TestRuntimeWorker(
        cast(
            AppConfig,
            SimpleNamespace(
                runtime=SimpleNamespace(request_timeout_seconds=30, lease_heartbeat_seconds=15)
            ),
        ),
        executor,
        database=cast(DatabaseManager, SimpleNamespace()),
        notifier=NullNotifier(),
    )
    worker.events = RecordingEvents()

    await worker.process_claim(
        _claim(runtime_payload={"active_skill": {"skill_id": "skill_test", "skill_version": 3}})
    )

    assert executor.request is not None
    assert executor.request.active_skill == RuntimeActiveSkill("skill_test", 3)
    assert executor.request.skill_context == RuntimeSkillContext(
        primary=RuntimeActiveSkill("skill_test", 3)
    )


@pytest.mark.asyncio
async def test_worker_restores_the_persisted_skill_context_checkpoint() -> None:
    executor = RecordingExecutor()
    worker = _TestRuntimeWorker(
        cast(
            AppConfig,
            SimpleNamespace(
                runtime=SimpleNamespace(request_timeout_seconds=30, lease_heartbeat_seconds=15)
            ),
        ),
        executor,
        database=cast(DatabaseManager, SimpleNamespace()),
        notifier=NullNotifier(),
    )
    worker.events = RecordingEvents()
    context = RuntimeSkillContext(
        primary=RuntimeActiveSkill("skill_primary", 3),
        supporting=(RuntimeActiveSkill("skill_supporting", 2),),
    )

    await worker.process_claim(
        _claim(
            runtime_payload={
                "skill_context": {
                    "schema_version": 1,
                    "primary": {"skill_id": "skill_primary", "skill_version": 3},
                    "supporting": [
                        {"skill_id": "skill_supporting", "skill_version": 2},
                    ],
                }
            }
        )
    )

    assert executor.request is not None
    assert executor.request.skill_context == context
    assert executor.request.active_skill == context.primary


@pytest.mark.asyncio
async def test_worker_passes_the_persisted_subagent_task_contract_to_runtime() -> None:
    executor = RecordingExecutor()
    worker = _TestRuntimeWorker(
        cast(
            AppConfig,
            SimpleNamespace(
                runtime=SimpleNamespace(request_timeout_seconds=30, lease_heartbeat_seconds=15)
            ),
        ),
        executor,
        database=cast(DatabaseManager, SimpleNamespace()),
        notifier=NullNotifier(),
    )
    worker.events = RecordingEvents()
    task: dict[str, object] = {
        "id": "task_review",
        "kind": "code_review",
        "budget": {"max_tool_calls": 2},
    }

    await worker.process_claim(_claim(subagent_task=task, runtime_depth=1))

    assert executor.request is not None
    assert executor.request.subagent_task == task
    assert executor.request.runtime_depth == 1


@pytest.mark.asyncio
async def test_worker_restores_taskboard_snapshot_and_pending_action() -> None:
    executor = RecordingExecutor()
    worker = _TestRuntimeWorker(
        cast(
            AppConfig,
            SimpleNamespace(
                runtime=SimpleNamespace(request_timeout_seconds=30, lease_heartbeat_seconds=15)
            ),
        ),
        executor,
        database=cast(DatabaseManager, SimpleNamespace()),
        notifier=NullNotifier(),
    )
    worker.events = RecordingEvents()
    board: dict[str, object] = {
        "board_id": "board_test",
        "status": "completed",
        "tasks": [],
    }
    snapshot: tuple[dict[str, object], ...] = ({"role": "system", "content": "root policy"},)
    action: dict[str, object] = {"action_id": "pending_test", "status": "approved"}

    await worker.process_claim(
        _claim(
            runtime_payload={
                "task_board": board,
                "resume_messages": list(snapshot),
                "pending_tool_action": action,
            }
        )
    )

    assert executor.request is not None
    assert executor.request.task_board == board
    assert executor.request.resume_messages == snapshot
    assert executor.request.pending_tool_action == action


@pytest.mark.asyncio
async def test_worker_maps_model_provider_failure_to_stable_event() -> None:
    worker = _TestRuntimeWorker(
        cast(
            AppConfig,
            SimpleNamespace(
                runtime=SimpleNamespace(request_timeout_seconds=30, lease_heartbeat_seconds=15)
            ),
        ),
        FailingExecutor(),
        database=cast(DatabaseManager, SimpleNamespace()),
        notifier=NullNotifier(),
    )
    events = RecordingEvents()
    worker.events = events
    await worker.process_claim(_claim())

    assert events.items[-1]["event_type"] == "ai.output.failed"
    assert events.items[-1]["data"] == {
        "code": "AI_PROVIDER_UNAVAILABLE",
        "message": "智能体运行服务暂时不可用，请稍后重试。",
        "runtime_execution_id": "runtime:interaction_test",
    }
    assert events.items[-1]["terminal_status"] == "failed"


@pytest.mark.asyncio
async def test_executor_completes_in_the_worker_call_without_background_task() -> None:
    executor = InProcessAgentRuntime(RecordingModel(), max_tool_rounds=2, timeout_seconds=5)
    events = RecordingEvents()

    await executor.execute(_request(), events)

    assert [item["event_type"] for item in events.items] == [
        "ai.input.processed",
        "ai.agent.plan.created",
        "ai.output.delta",
        "ai.output.completed",
    ]
    assert events.items[-1]["terminal_status"] == "completed"


class RecordingExecutor:
    def __init__(self) -> None:
        self.request: RuntimeRequest | None = None

    async def execute(self, request: RuntimeRequest, events: RuntimeEventSink) -> None:
        del events
        self.request = request


class FailingExecutor:
    async def execute(self, request: RuntimeRequest, events: RuntimeEventSink) -> None:
        del request, events
        raise ModelProviderError("provider unavailable")


class _TestRuntimeWorker(RuntimeWorker):
    async def _resume_context(self, claim: ClaimedInteraction) -> ResumeContext:
        del claim
        return ResumeContext()

    async def _release_lease(self, claim: ClaimedInteraction) -> None:
        del claim


class NullNotifier:
    async def publish_interaction_event(self, interaction_id: str) -> None:
        del interaction_id


def _profile() -> AgentRuntimeProfile:
    return AgentRuntimeProfile(
        llm=RuntimeLlmProfile(
            id="llm_test",
            provider="openai_compatible",
            model="model-test",
            base_url="https://models.example.test/v1",
            credential_envelope=TEST_CREDENTIAL_ENVELOPE,
        ),
        skills=(
            RuntimeSkillProfile(
                id="skill_test",
                name="reporting",
                description="Summarize reports",
                instructions="Use concise prose.",
                manifest={},
                version=3,
            ),
        ),
    )


def _request() -> RuntimeRequest:
    return RuntimeRequest(
        interaction_id="interaction_test",
        tenant_id="tenant_test",
        runtime_agent_id="agent_runtime_test",
        agent_id="agent_test",
        actor_type="anonymous",
        actor_id="visitor_test",
        entry_type="text",
        input_type="text",
        conversation_id=None,
        text="Summarize the report",
        request_id="req_test",
        profile=_profile(),
    )


def _claim(
    subagent_task: dict[str, object] | None = None,
    runtime_depth: int = 0,
    runtime_payload: dict[str, object] | None = None,
) -> ClaimedInteraction:
    return ClaimedInteraction(
        interaction_id="interaction_test",
        tenant_id="tenant_test",
        agent_id="agent_test",
        actor_type="anonymous",
        actor_id="visitor_test",
        entry_type="text",
        input_type="text",
        conversation_id=None,
        parent_interaction_id=None,
        root_interaction_id="interaction_test",
        subagent_task_id=None,
        runtime_depth=runtime_depth,
        execution_id="runtime:interaction_test",
        input_payload={
            "text": "Summarize the report",
            "audio_ref": None,
            "runtime_agent_id": "agent_runtime_test",
            "request_id": "req_test",
            "profile": profile_to_payload(_profile()),
            **({"subagent_task": subagent_task} if subagent_task is not None else {}),
            **(runtime_payload or {}),
        },
        enqueued_at=None,
        created_at=datetime.now(UTC),
    )
