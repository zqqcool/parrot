from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.agent_runtime import (
    AgentRuntimeProfile,
    AgentRuntimeProfileResolver,
    profile_to_payload,
)
from app.core.clock import utc_now
from app.core.errors import AppError
from app.core.ids import new_id
from app.infrastructure.db.session import DatabaseManager
from app.modules.agents.ports import AgentRuntimeTarget
from app.modules.interactions.event_store import InteractionEventNotifier
from app.modules.interactions.models import (
    ConversationMessage,
    IdempotencyRecord,
    Interaction,
    InteractionEvent,
)
from app.modules.interactions.runtime import RuntimePort, RuntimeRequest, RuntimeResult
from app.modules.interactions.schemas import (
    InteractionAccepted,
    InteractionEventView,
    InteractionView,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InteractionSubmission:
    actor_type: str
    actor_id: str
    entry_type: str
    input_type: str
    request_id: str
    idempotency_key: str
    text: str | None = None
    audio_ref: str | None = None
    conversation_id: str | None = None
    im_channel_id: str | None = None
    im_agent_binding_id: str | None = None
    external_message_id: str | None = None
    message_expires_at: datetime | None = None


class InteractionService:
    def __init__(
        self,
        session: AsyncSession,
        database: DatabaseManager,
        runtime: RuntimePort,
        event_notifier: InteractionEventNotifier | None = None,
        profile_resolver: AgentRuntimeProfileResolver | None = None,
    ) -> None:
        self.session = session
        self.database = database
        self.runtime = runtime
        self.event_notifier = event_notifier
        self.profile_resolver = profile_resolver

    async def submit(
        self,
        agent: AgentRuntimeTarget,
        submission: InteractionSubmission,
    ) -> InteractionAccepted:
        await self.database.set_tenant(self.session, agent.tenant_id)
        existing = await self._idempotent_result(
            agent.tenant_id,
            submission.actor_type,
            submission.actor_id,
            submission.entry_type,
            submission.idempotency_key,
        )
        if existing:
            return self._accepted(existing)
        profile = await self._profile_for(agent)
        interaction = await self._persist_submission(agent, submission, profile)
        request = self._runtime_request(agent, interaction, submission, profile)
        result = await self._prepare_runtime(request, interaction)
        await self._persist_runtime_acceptance(interaction, result)
        await self._dispatch_runtime(request)
        return self._accepted(interaction)

    async def _persist_submission(
        self,
        agent: AgentRuntimeTarget,
        submission: InteractionSubmission,
        profile: AgentRuntimeProfile | None,
    ) -> Interaction:
        interaction = Interaction(
            id=new_id("interaction"),
            tenant_id=agent.tenant_id,
            agent_id=agent.id,
            im_channel_id=submission.im_channel_id,
            im_agent_binding_id=submission.im_agent_binding_id,
            actor_type=submission.actor_type,
            actor_id=submission.actor_id,
            entry_type=submission.entry_type,
            input_type=submission.input_type,
            conversation_id=submission.conversation_id,
            transcript_expires_at=submission.message_expires_at,
            input_summary=(submission.text or submission.audio_ref or "")[:500],
            input_payload={
                "text": submission.text,
                "audio_ref": submission.audio_ref,
                "runtime_agent_id": agent.runtime_agent_id,
                "request_id": submission.request_id,
                "profile": profile_to_payload(profile) if profile is not None else None,
            },
        )
        interaction.root_interaction_id = interaction.id
        self.session.add(interaction)
        await self.session.flush()
        await self._persist_user_message(interaction, submission)
        self.session.add(self._accepted_event(agent.tenant_id, interaction.id, submission))
        self.session.add(
            IdempotencyRecord(
                id=new_id("idem"),
                tenant_id=agent.tenant_id,
                actor_type=submission.actor_type,
                actor_id=submission.actor_id,
                entry_type=submission.entry_type,
                idempotency_key=submission.idempotency_key,
                interaction_id=interaction.id,
            )
        )
        await self.session.flush()
        # Runtime work may outlive the request. Commit the durable interaction before the
        # adapter starts so event writers never race an uncommitted parent record.
        await self.session.commit()
        return interaction

    async def _persist_user_message(
        self, interaction: Interaction, submission: InteractionSubmission
    ) -> None:
        if (
            not submission.conversation_id
            or not submission.text
            or submission.entry_type == "schedule"
        ):
            return
        message = ConversationMessage(
            id=new_id("conversation_message"),
            tenant_id=interaction.tenant_id,
            interaction_id=interaction.id,
            sequence=0,
            agent_id=interaction.agent_id,
            im_channel_id=interaction.im_channel_id,
            im_agent_binding_id=interaction.im_agent_binding_id,
            actor_type=interaction.actor_type,
            actor_id=interaction.actor_id,
            conversation_id=submission.conversation_id,
            role="user",
            direction="inbound",
            external_message_id=submission.external_message_id,
            content=submission.text,
            expires_at=submission.message_expires_at,
        )
        self.session.add(message)

    @staticmethod
    def _runtime_request(
        agent: AgentRuntimeTarget,
        interaction: Interaction,
        submission: InteractionSubmission,
        profile: AgentRuntimeProfile | None,
    ) -> RuntimeRequest:
        return RuntimeRequest(
            interaction_id=interaction.id,
            tenant_id=agent.tenant_id,
            runtime_agent_id=agent.runtime_agent_id,
            actor_type=submission.actor_type,
            actor_id=submission.actor_id,
            entry_type=submission.entry_type,
            input_type=submission.input_type,
            agent_id=agent.id,
            conversation_id=submission.conversation_id,
            text=submission.text,
            audio_ref=submission.audio_ref,
            request_id=submission.request_id,
            profile=profile,
        )

    async def _prepare_runtime(
        self, request: RuntimeRequest, interaction: Interaction
    ) -> RuntimeResult:
        try:
            return await self.runtime.prepare(request)
        except AppError:
            raise
        except Exception as exc:
            logger.exception(
                "AI runtime preparation failed",
                extra={
                    "request_id": request.request_id,
                    "tenant_id": request.tenant_id,
                    "interaction_id": interaction.id,
                },
            )
            await self.database.set_tenant(self.session, request.tenant_id)
            interaction.status = "failed"
            await self.session.commit()
            raise AppError(
                "AI_PROVIDER_UNAVAILABLE",
                "AI runtime is unavailable",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            ) from exc

    async def _persist_runtime_acceptance(
        self, interaction: Interaction, result: RuntimeResult
    ) -> None:
        await self.database.set_tenant(self.session, interaction.tenant_id)
        interaction.status = result.status
        interaction.runtime_execution_id = result.execution_id
        if result.execution_id is not None and result.recovery_lease_seconds is not None:
            interaction.runtime_recovery_lease_owner = f"runtime:{result.execution_id}"
            interaction.runtime_recovery_lease_until = utc_now() + timedelta(
                seconds=result.recovery_lease_seconds
            )
        await self.session.commit()

    async def _dispatch_runtime(self, request: RuntimeRequest) -> None:
        try:
            await self.runtime.dispatch(request)
        except AppError:
            raise
        except Exception as exc:
            logger.exception(
                "AI runtime dispatch failed",
                extra={
                    "request_id": request.request_id,
                    "tenant_id": request.tenant_id,
                    "interaction_id": request.interaction_id,
                },
            )
            raise AppError(
                "AI_PROVIDER_UNAVAILABLE",
                "AI runtime is unavailable",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            ) from exc

    async def _profile_for(self, agent: AgentRuntimeTarget) -> AgentRuntimeProfile | None:
        if self.profile_resolver is None:
            return None
        return await self.profile_resolver.resolve(agent.tenant_id, agent.id)

    @staticmethod
    def _accepted_event(
        tenant_id: str, interaction_id: str, submission: InteractionSubmission
    ) -> InteractionEvent:
        return InteractionEvent(
            id=new_id("event"),
            tenant_id=tenant_id,
            interaction_id=interaction_id,
            type="ai.interaction.accepted",
            request_id=submission.request_id,
            sequence=1,
            data={"interaction_id": interaction_id, "status": "accepted"},
        )

    async def get_owned(
        self,
        interaction_id: str,
        tenant_id: str,
        actor_type: str,
        actor_id: str,
    ) -> InteractionView:
        await self.database.set_tenant(self.session, tenant_id)
        result = await self.session.execute(
            select(Interaction).where(
                Interaction.id == interaction_id,
                Interaction.tenant_id == tenant_id,
                Interaction.actor_type == actor_type,
                Interaction.actor_id == actor_id,
                Interaction.runtime_depth == 0,
            )
        )
        model = result.scalar_one_or_none()
        if model is None:
            raise AppError(
                "AI_INTERACTION_NOT_FOUND", "Interaction not found", status.HTTP_404_NOT_FOUND
            )
        return self._view(model)

    async def list_events(
        self,
        interaction_id: str,
        tenant_id: str,
        actor_type: str,
        actor_id: str,
    ) -> list[InteractionEventView]:
        await self.get_owned(interaction_id, tenant_id, actor_type, actor_id)
        result = await self.session.execute(
            select(InteractionEvent)
            .where(InteractionEvent.interaction_id == interaction_id)
            .order_by(InteractionEvent.sequence)
        )
        return [
            InteractionEventView(
                type=item.type,
                event_id=item.id,
                request_id=item.request_id,
                occurred_at=item.created_at,
                sequence=item.sequence,
                data=item.data,
            )
            for item in result.scalars()
        ]

    async def _idempotent_result(
        self,
        tenant_id: str,
        actor_type: str,
        actor_id: str,
        entry_type: str,
        key: str,
    ) -> Interaction | None:
        result = await self.session.execute(
            select(Interaction)
            .join(IdempotencyRecord, IdempotencyRecord.interaction_id == Interaction.id)
            .where(
                IdempotencyRecord.tenant_id == tenant_id,
                IdempotencyRecord.actor_type == actor_type,
                IdempotencyRecord.actor_id == actor_id,
                IdempotencyRecord.entry_type == entry_type,
                IdempotencyRecord.idempotency_key == key,
            )
        )
        return result.scalar_one_or_none()

    def _accepted(self, model: Interaction) -> InteractionAccepted:
        return InteractionAccepted(
            interaction_id=model.id,
            status=model.status,
        )

    @staticmethod
    def _view(model: Interaction) -> InteractionView:
        return InteractionView(
            interaction_id=model.id,
            tenant_id=model.tenant_id,
            agent_id=model.agent_id,
            entry_type=model.entry_type,
            input_type=model.input_type,
            status=model.status,
            runtime_execution_id=model.runtime_execution_id,
            im_channel_id=model.im_channel_id,
            im_agent_binding_id=model.im_agent_binding_id,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
