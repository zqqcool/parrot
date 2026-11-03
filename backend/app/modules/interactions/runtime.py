from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.core.agent_runtime import AgentRuntimeProfile


@dataclass(frozen=True)
class RuntimeActiveSkill:
    skill_id: str
    skill_version: int


@dataclass(frozen=True)
class RuntimeSkillContext:
    primary: RuntimeActiveSkill | None = None
    supporting: tuple[RuntimeActiveSkill, ...] = ()


@dataclass(frozen=True)
class RuntimeRequest:
    interaction_id: str
    tenant_id: str
    runtime_agent_id: str
    agent_id: str
    actor_type: str
    actor_id: str
    entry_type: str
    input_type: str
    conversation_id: str | None = None
    task_board: dict[str, object] | None = None
    resume_messages: tuple[dict[str, object], ...] = ()
    pending_tool_action: dict[str, object] | None = None
    active_skill: RuntimeActiveSkill | None = None
    skill_context: RuntimeSkillContext | None = None
    subagent_task: dict[str, object] | None = None
    parent_interaction_id: str | None = None
    subagent_task_id: str | None = None
    runtime_depth: int = 0
    resume_assistant_message: str | None = None
    control_after_sequence: int = 0
    output_id: str | None = None
    text: str | None = None
    audio_ref: str | None = None
    request_id: str = ""
    profile: AgentRuntimeProfile | None = None
    control_reader: RuntimeControlReader | None = None
    enqueued_at: datetime | None = None


@dataclass(frozen=True)
class RuntimeResult:
    status: str
    execution_id: str | None = None
    recovery_lease_seconds: int | None = None


@dataclass(frozen=True)
class RuntimeControlRequest:
    interaction_id: str
    tenant_id: str
    actor_type: str
    actor_id: str
    execution_id: str | None
    request_id: str
    message: str | None = None
    runtime_event_sequence: int = 0
    runtime_agent_id: str | None = None
    entry_type: str | None = None
    input_type: str | None = None
    text: str | None = None
    audio_ref: str | None = None
    profile: AgentRuntimeProfile | None = None
    resume_from_waiting: bool = False


@dataclass(frozen=True)
class RuntimeControlState:
    cancel_requested: bool = False
    steering_messages: tuple[str, ...] = ()


class RuntimeControlReader(Protocol):
    async def consume(self, request: RuntimeRequest) -> RuntimeControlState: ...


class RuntimeEventSink(Protocol):
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
    ) -> object: ...

    async def record_trace(
        self,
        *,
        tenant_id: str,
        interaction_id: str,
        trace_type: str,
        data: dict[str, object],
        lease_owner: str | None = None,
    ) -> object: ...


class RuntimePort(Protocol):
    async def prepare(self, request: RuntimeRequest) -> RuntimeResult: ...

    async def dispatch(self, request: RuntimeRequest) -> None: ...

    async def cancel(self, request: RuntimeControlRequest, events: RuntimeEventSink) -> None: ...

    async def steer(self, request: RuntimeControlRequest, events: RuntimeEventSink) -> None: ...

    async def recover(self, request: RuntimeControlRequest, events: RuntimeEventSink) -> None: ...
