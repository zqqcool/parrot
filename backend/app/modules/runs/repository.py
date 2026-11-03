from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Select, and_, case, delete, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.core.clock import utc_now
from app.modules.interactions.models import (
    ConversationMessage,
    Interaction,
    InteractionDiagnosticTrace,
    InteractionEvent,
)

TERMINAL_RUN_STATUSES = ("completed", "partial", "failed", "cancelled")


@dataclass(frozen=True)
class RunRequesterRow:
    actor_type: str
    actor_id: str
    run_count: int
    active_run_count: int
    latest_run_at: datetime


@dataclass(frozen=True)
class ConversationSummaryRow:
    conversation_id: str
    agent_id: str
    message_count: int
    active_run_count: int
    latest_message_at: datetime


@dataclass(frozen=True)
class ConversationMessageRow:
    id: str
    interaction_id: str
    role: str
    content: str
    run_status: str
    created_at: datetime


class RunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(
        self,
        tenant_id: str,
        *,
        status: str | None,
        agent_id: str | None,
        actor_type: str | None,
        actor_id: str | None,
        limit: int,
    ) -> list[Interaction]:
        statement: Select[tuple[Interaction]] = select(Interaction).where(
            Interaction.tenant_id == tenant_id
        )
        if status:
            statement = statement.where(Interaction.status == status)
        if agent_id:
            statement = statement.where(Interaction.agent_id == agent_id)
        if actor_type and actor_id:
            statement = statement.where(
                Interaction.actor_type == actor_type,
                Interaction.actor_id == actor_id,
            )
        rows = await self.session.scalars(
            statement.order_by(Interaction.created_at.desc()).limit(limit)
        )
        return list(rows)

    async def list_requesters(
        self,
        tenant_id: str,
        *,
        actor_type: str | None = None,
        query: str | None = None,
        user_ids: tuple[str, ...] = (),
        limit: int,
    ) -> list[RunRequesterRow]:
        statement = (
            select(
                Interaction.actor_type,
                Interaction.actor_id,
                func.count(Interaction.id).label("run_count"),
                func.sum(
                    case((Interaction.status.not_in(TERMINAL_RUN_STATUSES), 1), else_=0)
                ).label("active_run_count"),
                func.max(Interaction.created_at).label("latest_run_at"),
            )
            .where(
                Interaction.tenant_id == tenant_id,
                Interaction.actor_type != "schedule",
            )
            .group_by(Interaction.actor_type, Interaction.actor_id)
            .order_by(
                func.max(Interaction.created_at).desc(),
                Interaction.actor_type,
                Interaction.actor_id,
            )
        )
        if actor_type:
            statement = statement.where(Interaction.actor_type == actor_type)
        normalized = query.strip() if query else ""
        if normalized:
            requester_matches = [Interaction.actor_id.icontains(normalized, autoescape=True)]
            if user_ids:
                requester_matches.append(
                    and_(Interaction.actor_type == "user", Interaction.actor_id.in_(user_ids))
                )
            statement = statement.where(or_(*requester_matches))
        rows = await self.session.execute(statement.limit(limit))
        return [
            RunRequesterRow(
                actor_type=actor_type,
                actor_id=actor_id,
                run_count=int(run_count),
                active_run_count=int(active_run_count or 0),
                latest_run_at=latest_run_at,
            )
            for actor_type, actor_id, run_count, active_run_count, latest_run_at in rows.tuples()
        ]

    async def get(self, tenant_id: str, run_id: str) -> Interaction | None:
        return await self.session.scalar(
            select(Interaction).where(Interaction.tenant_id == tenant_id, Interaction.id == run_id)
        )

    async def list_events(self, tenant_id: str, run_id: str) -> list[InteractionEvent]:
        rows = await self.session.scalars(
            select(InteractionEvent)
            .where(
                InteractionEvent.tenant_id == tenant_id,
                InteractionEvent.interaction_id == run_id,
            )
            .order_by(InteractionEvent.sequence)
        )
        return list(rows)

    async def list_diagnostic_traces(
        self, tenant_id: str, run_id: str
    ) -> list[InteractionDiagnosticTrace]:
        rows = await self.session.scalars(
            select(InteractionDiagnosticTrace)
            .where(
                InteractionDiagnosticTrace.tenant_id == tenant_id,
                InteractionDiagnosticTrace.interaction_id == run_id,
                or_(
                    InteractionDiagnosticTrace.expires_at.is_(None),
                    InteractionDiagnosticTrace.expires_at > utc_now(),
                ),
            )
            .order_by(InteractionDiagnosticTrace.sequence)
        )
        return list(rows)

    async def list_conversations(
        self, tenant_id: str, *, actor_type: str, actor_id: str, limit: int
    ) -> list[ConversationSummaryRow]:
        message = ConversationMessage
        interaction = Interaction
        statement = (
            select(
                message.conversation_id,
                message.agent_id,
                func.count(message.id).label("message_count"),
                func.count(
                    func.distinct(
                        case((interaction.status.not_in(TERMINAL_RUN_STATUSES), interaction.id))
                    )
                ).label("active_run_count"),
                func.max(message.created_at).label("latest_message_at"),
            )
            .join(
                interaction,
                and_(
                    interaction.tenant_id == message.tenant_id,
                    interaction.id == message.interaction_id,
                ),
            )
            .where(*self._visible_transcript_filters(tenant_id, actor_type, actor_id))
            .group_by(message.conversation_id, message.agent_id)
            .order_by(func.max(message.created_at).desc())
            .limit(limit)
        )
        rows = await self.session.execute(statement)
        return [
            ConversationSummaryRow(
                conversation_id=conversation_id,
                agent_id=agent_id,
                message_count=int(message_count),
                active_run_count=int(active_run_count or 0),
                latest_message_at=latest_message_at,
            )
            for (
                conversation_id,
                agent_id,
                message_count,
                active_run_count,
                latest_message_at,
            ) in rows.tuples()
        ]

    async def list_conversation_messages(
        self,
        tenant_id: str,
        *,
        actor_type: str,
        actor_id: str,
        conversation_id: str,
    ) -> list[ConversationMessageRow]:
        message = ConversationMessage
        interaction = Interaction
        statement = (
            select(message, interaction.status)
            .join(
                interaction,
                and_(
                    interaction.tenant_id == message.tenant_id,
                    interaction.id == message.interaction_id,
                ),
            )
            .where(
                *self._visible_transcript_filters(tenant_id, actor_type, actor_id),
                message.conversation_id == conversation_id,
            )
            .order_by(message.created_at, message.id)
        )
        rows = await self.session.execute(statement)
        return [
            ConversationMessageRow(
                id=message.id,
                interaction_id=message.interaction_id,
                role=message.role,
                content=message.content,
                run_status=run_status,
                created_at=message.created_at,
            )
            for message, run_status in rows.tuples()
        ]

    async def count_legacy_chat_runs(self, tenant_id: str) -> int:
        statement = select(func.count(Interaction.id)).where(*self._legacy_chat_filters(tenant_id))
        return int(await self.session.scalar(statement) or 0)

    async def delete_legacy_chat_runs(self, tenant_id: str) -> int:
        candidate_count = await self.count_legacy_chat_runs(tenant_id)
        if candidate_count:
            statement = delete(Interaction).where(*self._legacy_chat_filters(tenant_id))
            await self.session.execute(statement)
        return candidate_count

    @staticmethod
    def _visible_transcript_filters(
        tenant_id: str, actor_type: str, actor_id: str
    ) -> tuple[ColumnElement[bool], ...]:
        now = utc_now()
        return (
            ConversationMessage.tenant_id == tenant_id,
            ConversationMessage.actor_type == actor_type,
            ConversationMessage.actor_id == actor_id,
            ConversationMessage.status == "active",
            or_(ConversationMessage.expires_at.is_(None), ConversationMessage.expires_at > now),
        )

    @staticmethod
    def _legacy_chat_filters(tenant_id: str) -> tuple[ColumnElement[bool], ...]:
        has_transcript = exists(
            select(ConversationMessage.id).where(
                ConversationMessage.tenant_id == Interaction.tenant_id,
                ConversationMessage.interaction_id == Interaction.id,
            )
        )
        return (
            Interaction.tenant_id == tenant_id,
            Interaction.actor_type.in_(("user", "anonymous")),
            Interaction.entry_type == "websocket",
            Interaction.parent_interaction_id.is_(None),
            Interaction.runtime_depth == 0,
            Interaction.status.in_(TERMINAL_RUN_STATUSES),
            Interaction.conversation_id.is_(None),
            ~has_transcript,
        )
