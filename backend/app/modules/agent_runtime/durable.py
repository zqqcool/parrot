from __future__ import annotations

import logging
import os
import socket
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from sqlalchemy import or_, select, update
from sqlalchemy.orm.attributes import flag_modified

from app.core.agent_runtime import profile_from_payload
from app.core.clock import SYSTEM_CLOCK, Clock
from app.core.config import AppConfig
from app.core.error_messages import public_error_message
from app.core.ids import new_id
from app.core.task_dispatch import TaskDispatcher
from app.infrastructure.db.session import DatabaseManager
from app.infrastructure.redis import RedisManager
from app.modules.agent_runtime.active_skill import runtime_skill_context_from_payload
from app.modules.agent_runtime.contracts import ModelProviderError
from app.modules.agent_runtime.control import InteractionControlReader
from app.modules.agent_runtime.final_renderer import (
    FinalRenderProtocolError,
    FinalRenderProviderError,
)
from app.modules.agent_runtime.final_response import FinalResponseProtocolError
from app.modules.agent_runtime.lease import InteractionLeaseHeartbeat
from app.modules.agent_runtime.lease_events import LeaseBoundEventSink
from app.modules.agent_runtime.planner import AgentPlanProtocolError
from app.modules.agent_runtime.runtime_payload import (
    payload_mapping,
    payload_mapping_tuple,
    payload_string,
)
from app.modules.agent_runtime.subagent_dispatcher import SubagentDispatcherPort
from app.modules.interactions.event_store import InteractionEventNotifier, InteractionEventStore
from app.modules.interactions.models import Interaction, InteractionEvent
from app.modules.interactions.runtime import (
    RuntimeControlRequest,
    RuntimeEventSink,
    RuntimePort,
    RuntimeRequest,
    RuntimeResult,
)

logger = logging.getLogger(__name__)
_IN_PROCESS_EXECUTION_PREFIX = "runtime:"
_CLAIMABLE_STATUSES = ("accepted", "running")


class AgentRuntimeExecutor(Protocol):
    async def execute(self, request: RuntimeRequest, events: RuntimeEventSink) -> None: ...


class DurableInProcessRuntime(RuntimePort):
    """Dispatches work durably; it never starts an Agent task in the Web process."""

    def __init__(
        self,
        dispatcher: TaskDispatcher,
        database: DatabaseManager | None = None,
        *,
        clock: Clock = SYSTEM_CLOCK,
    ) -> None:
        self._dispatcher = dispatcher
        self._database = database
        self._clock = clock

    async def prepare(self, request: RuntimeRequest) -> RuntimeResult:
        if request.profile is None:
            raise ValueError("In-process agent runtime requires an agent runtime profile")
        return RuntimeResult(
            status="accepted",
            execution_id=f"{_IN_PROCESS_EXECUTION_PREFIX}{request.interaction_id}",
            recovery_lease_seconds=None,
        )

    async def dispatch(self, request: RuntimeRequest) -> None:
        await self._stamp_enqueued(request.tenant_id, request.interaction_id)
        await self._dispatcher.dispatch_runtime(request.tenant_id, request.interaction_id)

    async def cancel(self, request: RuntimeControlRequest, events: RuntimeEventSink) -> None:
        await events.append(
            tenant_id=request.tenant_id,
            interaction_id=request.interaction_id,
            request_id=request.request_id,
            event_type="ai.interaction.cancel.requested",
            data={"runtime_execution_id": request.execution_id},
        )

    async def steer(self, request: RuntimeControlRequest, events: RuntimeEventSink) -> None:
        if not request.message or not request.message.strip():
            raise ValueError("In-process steering requires a message")
        persisted = await events.append(
            tenant_id=request.tenant_id,
            interaction_id=request.interaction_id,
            request_id=request.request_id,
            event_type="ai.interaction.steer.requested",
            data={"message": request.message.strip(), "runtime_execution_id": request.execution_id},
            terminal_status="accepted" if request.resume_from_waiting else None,
        )
        if request.resume_from_waiting and persisted is not None:
            await self.dispatch(
                RuntimeRequest(
                    interaction_id=request.interaction_id,
                    tenant_id=request.tenant_id,
                    runtime_agent_id=request.runtime_agent_id or "",
                    agent_id="",
                    actor_type=request.actor_type,
                    actor_id=request.actor_id,
                    entry_type=request.entry_type or "websocket",
                    input_type=request.input_type or "text",
                    request_id=request.request_id,
                )
            )

    async def recover(self, request: RuntimeControlRequest, events: RuntimeEventSink) -> None:
        # RuntimeWorker claims durable in-process interactions directly. The remote recovery
        # adapter is deliberately not reused because it would create a competing lease owner.
        del request, events

    async def _stamp_enqueued(self, tenant_id: str, interaction_id: str) -> None:
        if self._database is None:
            return
        async with self._database.session() as session:
            await self._database.set_tenant(session, tenant_id)
            interaction = await session.scalar(
                select(Interaction).where(
                    Interaction.tenant_id == tenant_id,
                    Interaction.id == interaction_id,
                )
            )
            if interaction is None:
                return
            payload = dict(interaction.input_payload or {})
            payload["runtime_enqueued_at"] = self._clock.now().isoformat()
            interaction.input_payload = payload
            flag_modified(interaction, "input_payload")
            await session.commit()


@dataclass(frozen=True)
class ClaimedInteraction:
    interaction_id: str
    tenant_id: str
    agent_id: str
    actor_type: str
    actor_id: str
    entry_type: str
    input_type: str
    conversation_id: str | None
    parent_interaction_id: str | None
    root_interaction_id: str | None
    subagent_task_id: str | None
    runtime_depth: int
    execution_id: str
    input_payload: dict[str, object]
    enqueued_at: datetime | None
    created_at: datetime


class RuntimeWorker:
    """Lease-fenced executor invoked by the TaskIQ runtime task."""

    def __init__(
        self,
        settings: AppConfig,
        executor: AgentRuntimeExecutor,
        *,
        database: DatabaseManager | None = None,
        notifier: InteractionEventNotifier | None = None,
        subagent_dispatcher: SubagentDispatcherPort | None = None,
        clock: Clock = SYSTEM_CLOCK,
    ) -> None:
        self.settings = settings
        self.database = database or DatabaseManager(settings.database)
        self.executor = executor
        self._redis = RedisManager(settings.redis) if notifier is None else None
        event_notifier = notifier or self._redis
        self.events: RuntimeEventSink = InteractionEventStore(self.database, event_notifier)
        self._subagent_dispatcher = subagent_dispatcher
        self._clock = clock
        self.lease_owner = f"{socket.gethostname()}:{os.getpid()}:agent-runtime"
        self.lease_seconds = settings.runtime.request_timeout_seconds + 30

    async def close(self) -> None:
        try:
            return
        finally:
            if self._redis is not None:
                await self._redis.close()
            await self.database.dispose()

    async def process(self, tenant_id: str, interaction_id: str) -> bool:
        claim = await self._claim(tenant_id, interaction_id)
        if claim is None:
            return False
        await self.process_claim(claim)
        return True

    async def _claim(self, tenant_id: str, interaction_id: str) -> ClaimedInteraction | None:
        now = self._clock.now()
        async with self.database.session() as session:
            await self.database.set_tenant(session, tenant_id)
            interaction = await session.scalar(
                select(Interaction)
                .where(
                    Interaction.tenant_id == tenant_id,
                    Interaction.id == interaction_id,
                    Interaction.status.in_(_CLAIMABLE_STATUSES),
                    or_(
                        Interaction.runtime_recovery_lease_until.is_(None),
                        Interaction.runtime_recovery_lease_until < now,
                    ),
                )
                .order_by(Interaction.created_at)
                .with_for_update(skip_locked=True)
            )
            if interaction is None:
                return None
            interaction.status = "running"
            interaction.runtime_execution_id = (
                interaction.runtime_execution_id
                or f"{_IN_PROCESS_EXECUTION_PREFIX}{interaction.id}"
            )
            execution_id = interaction.runtime_execution_id
            interaction.runtime_recovery_lease_owner = self.lease_owner
            interaction.runtime_recovery_lease_until = now + timedelta(seconds=self.lease_seconds)
            await session.flush()
            if execution_id is None:
                return None
            return ClaimedInteraction(
                interaction_id=interaction.id,
                tenant_id=interaction.tenant_id,
                agent_id=interaction.agent_id,
                actor_type=interaction.actor_type,
                actor_id=interaction.actor_id,
                entry_type=interaction.entry_type,
                input_type=interaction.input_type,
                conversation_id=interaction.conversation_id,
                parent_interaction_id=interaction.parent_interaction_id,
                root_interaction_id=interaction.root_interaction_id,
                subagent_task_id=interaction.subagent_task_id,
                runtime_depth=interaction.runtime_depth,
                execution_id=execution_id,
                input_payload=interaction.input_payload,
                enqueued_at=_enqueued_at(interaction.input_payload),
                created_at=interaction.created_at,
            )

    async def process_claim(self, claim: ClaimedInteraction) -> None:
        request_id = payload_string(claim.input_payload, "request_id") or new_id("request_runtime")
        logger.info(
            "Runtime worker claimed interaction request_id=%s interaction_id=%s "
            "tenant_id=%s agent_id=%s",
            request_id,
            claim.interaction_id,
            claim.tenant_id,
            claim.agent_id,
        )
        events = LeaseBoundEventSink(self.events, self.lease_owner)
        started = await events.append(
            tenant_id=claim.tenant_id,
            interaction_id=claim.interaction_id,
            request_id=request_id,
            event_type="ai.interaction.status",
            data={"status": "running", "runtime_execution_id": claim.execution_id},
        )
        if started is None:
            return
        request: RuntimeRequest | None = None
        heartbeat = InteractionLeaseHeartbeat(
            self.database,
            tenant_id=claim.tenant_id,
            interaction_id=claim.interaction_id,
            owner=self.lease_owner,
            lease_seconds=self.lease_seconds,
            interval_seconds=self.settings.runtime.lease_heartbeat_seconds,
        )
        heartbeat.start()
        try:
            request = _runtime_request(
                claim,
                request_id,
                InteractionControlReader(self.database),
                await self._resume_context(claim),
                new_id("output"),
            )
            await self.executor.execute(request, events)
            logger.info(
                "Runtime worker completed interaction request_id=%s interaction_id=%s",
                request_id,
                claim.interaction_id,
            )
            if heartbeat.lost:
                logger.warning(
                    "Runtime worker lost its interaction lease",
                    extra={"tenant_id": claim.tenant_id, "interaction_id": claim.interaction_id},
                )
                return
        except FinalRenderProtocolError as error:
            await self._fail(
                claim,
                request_id,
                "AI_RESPONSE_PROTOCOL_INVALID",
                events,
                output_id=error.output_id,
            )
        except (AgentPlanProtocolError, FinalResponseProtocolError):
            await self._fail(claim, request_id, "AI_RESPONSE_PROTOCOL_INVALID", events)
        except FinalRenderProviderError as error:
            await self._fail(
                claim,
                request_id,
                "AI_PROVIDER_UNAVAILABLE",
                events,
                output_id=error.output_id,
            )
        except ModelProviderError:
            await self._fail(claim, request_id, "AI_PROVIDER_UNAVAILABLE", events)
        except TimeoutError:
            await self._fail(claim, request_id, "AI_OUTPUT_STREAM_INTERRUPTED", events)
        except Exception:
            logger.exception(
                "In-process agent worker failed",
                extra={
                    "request_id": request_id,
                    "tenant_id": claim.tenant_id,
                    "interaction_id": claim.interaction_id,
                },
            )
            await self._fail(claim, request_id, "AI_INTERNAL_ERROR", events)
        finally:
            await heartbeat.stop()
            if self._subagent_dispatcher is not None and request is not None and not heartbeat.lost:
                await self._subagent_dispatcher.settle_child(request, self.events)
            await self._release_lease(claim)

    async def _fail(
        self,
        claim: ClaimedInteraction,
        request_id: str,
        code: str,
        events: RuntimeEventSink,
        *,
        output_id: str | None = None,
    ) -> None:
        await events.append(
            tenant_id=claim.tenant_id,
            interaction_id=claim.interaction_id,
            request_id=request_id,
            event_type="ai.output.failed",
            data={
                "code": code,
                "message": public_error_message(code),
                "runtime_execution_id": claim.execution_id,
                **({"output_id": output_id} if output_id else {}),
            },
            terminal_status="failed",
        )

    async def _release_lease(self, claim: ClaimedInteraction) -> None:
        async with self.database.session() as session:
            await self.database.set_tenant(session, claim.tenant_id)
            await session.execute(
                update(Interaction)
                .where(
                    Interaction.tenant_id == claim.tenant_id,
                    Interaction.id == claim.interaction_id,
                    Interaction.runtime_recovery_lease_owner == self.lease_owner,
                )
                .values(runtime_recovery_lease_owner=None, runtime_recovery_lease_until=None)
            )

    async def _resume_context(self, claim: ClaimedInteraction) -> ResumeContext:
        async with self.database.session() as session:
            await self.database.set_tenant(session, claim.tenant_id)
            event = await session.scalar(
                select(InteractionEvent)
                .where(
                    InteractionEvent.tenant_id == claim.tenant_id,
                    InteractionEvent.interaction_id == claim.interaction_id,
                    InteractionEvent.type == "ai.output.completed",
                )
                .order_by(InteractionEvent.sequence.desc())
                .limit(1)
            )
        if event is None or event.data.get("runtime_status") != "waiting_user_input":
            return ResumeContext()
        content = event.data.get("content")
        return ResumeContext(
            assistant_message=content if isinstance(content, str) else None,
            control_after_sequence=event.sequence,
        )


@dataclass(frozen=True)
class ResumeContext:
    assistant_message: str | None = None
    control_after_sequence: int = 0


def _runtime_request(
    claim: ClaimedInteraction,
    request_id: str,
    control_reader: InteractionControlReader,
    resume_context: ResumeContext,
    output_turn_id: str,
) -> RuntimeRequest:
    profile = profile_from_payload(claim.input_payload.get("profile"))
    runtime_agent_id = payload_string(claim.input_payload, "runtime_agent_id")
    if profile is None or runtime_agent_id is None:
        raise ModelProviderError("In-process interaction snapshot is incomplete")
    skill_context = runtime_skill_context_from_payload(claim.input_payload)
    if skill_context is None:
        raise ModelProviderError("In-process Skill context checkpoint is invalid")
    return RuntimeRequest(
        interaction_id=claim.interaction_id,
        tenant_id=claim.tenant_id,
        runtime_agent_id=runtime_agent_id,
        agent_id=claim.agent_id,
        actor_type=claim.actor_type,
        actor_id=claim.actor_id,
        entry_type=claim.entry_type,
        input_type=claim.input_type,
        conversation_id=claim.conversation_id,
        task_board=payload_mapping(claim.input_payload, "task_board"),
        resume_messages=payload_mapping_tuple(claim.input_payload, "resume_messages"),
        pending_tool_action=payload_mapping(claim.input_payload, "pending_tool_action"),
        active_skill=skill_context.primary,
        skill_context=skill_context,
        subagent_task=payload_mapping(claim.input_payload, "subagent_task"),
        parent_interaction_id=claim.parent_interaction_id,
        subagent_task_id=claim.subagent_task_id,
        runtime_depth=claim.runtime_depth,
        resume_assistant_message=resume_context.assistant_message,
        control_after_sequence=resume_context.control_after_sequence,
        output_id=output_turn_id,
        text=payload_string(claim.input_payload, "text"),
        audio_ref=payload_string(claim.input_payload, "audio_ref"),
        request_id=request_id,
        profile=profile,
        control_reader=control_reader,
        enqueued_at=claim.enqueued_at or claim.created_at,
    )


def _enqueued_at(payload: dict[str, object]) -> datetime | None:
    raw = payload.get("runtime_enqueued_at")
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        value = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value
