from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from sqlalchemy import and_, func, select

from app.infrastructure.db.session import DatabaseManager
from app.modules.interactions.models import ConversationMessage

_CONTROL_TAG_RE = re.compile(r"</?\s*(?:memory-context|conversation-history)\s*>", re.I)


@dataclass(frozen=True)
class ConversationHistoryContext:
    tenant_id: str
    agent_id: str
    actor_type: str
    actor_id: str
    interaction_id: str
    conversation_id: str | None


@dataclass(frozen=True)
class ConversationTurn:
    """One persisted user request and its optional completed assistant response."""

    interaction_id: str
    user_content: str
    user_occurred_at: datetime | None = None
    assistant_content: str | None = None
    assistant_occurred_at: datetime | None = None

    @property
    def status(self) -> str:
        return "completed" if self.assistant_content else "incomplete"


@dataclass(frozen=True)
class ConversationHistoryMessage:
    """One native user or assistant message restored for a resumed interaction."""

    role: str
    content: str
    occurred_at: datetime | None = None


class ConversationHistoryPort(Protocol):
    async def recent(
        self, context: ConversationHistoryContext, *, turns: int, max_tokens: int
    ) -> tuple[ConversationTurn, ...]: ...

    async def resume_messages(
        self,
        context: ConversationHistoryContext,
        *,
        through_sequence: int,
        max_tokens: int,
    ) -> tuple[ConversationHistoryMessage, ...]: ...


class SqlConversationHistory:
    def __init__(self, database: DatabaseManager) -> None:
        self._database = database

    async def recent(
        self, context: ConversationHistoryContext, *, turns: int, max_tokens: int
    ) -> tuple[ConversationTurn, ...]:
        if not context.conversation_id:
            return ()
        async with self._database.session() as session:
            await self._database.set_tenant(session, context.tenant_id)
            filters = (
                ConversationMessage.tenant_id == context.tenant_id,
                ConversationMessage.agent_id == context.agent_id,
                ConversationMessage.actor_type == context.actor_type,
                ConversationMessage.actor_id == context.actor_id,
                ConversationMessage.conversation_id == context.conversation_id,
                ConversationMessage.interaction_id != context.interaction_id,
                ConversationMessage.status == "active",
            )
            latest_turns = (
                select(
                    ConversationMessage.tenant_id.label("tenant_id"),
                    ConversationMessage.interaction_id.label("interaction_id"),
                    func.max(ConversationMessage.created_at).label("latest_at"),
                )
                .where(*filters)
                .group_by(ConversationMessage.tenant_id, ConversationMessage.interaction_id)
                .order_by(func.max(ConversationMessage.created_at).desc())
                .limit(turns)
                .subquery()
            )
            statement = (
                select(ConversationMessage)
                .join(
                    latest_turns,
                    and_(
                        ConversationMessage.tenant_id == latest_turns.c.tenant_id,
                        ConversationMessage.interaction_id == latest_turns.c.interaction_id,
                    ),
                )
                .order_by(
                    latest_turns.c.latest_at.desc(),
                    ConversationMessage.sequence.desc(),
                    ConversationMessage.created_at.desc(),
                )
            )
            rows = tuple(await session.scalars(statement))
        return bounded_turns(rows, max_tokens, max_turns=turns)

    async def resume_messages(
        self,
        context: ConversationHistoryContext,
        *,
        through_sequence: int,
        max_tokens: int,
    ) -> tuple[ConversationHistoryMessage, ...]:
        if not context.conversation_id or through_sequence <= 0:
            return ()
        async with self._database.session() as session:
            await self._database.set_tenant(session, context.tenant_id)
            statement = (
                select(ConversationMessage)
                .where(
                    ConversationMessage.tenant_id == context.tenant_id,
                    ConversationMessage.agent_id == context.agent_id,
                    ConversationMessage.actor_type == context.actor_type,
                    ConversationMessage.actor_id == context.actor_id,
                    ConversationMessage.conversation_id == context.conversation_id,
                    ConversationMessage.interaction_id == context.interaction_id,
                    ConversationMessage.sequence <= through_sequence,
                    ConversationMessage.status == "active",
                )
                .order_by(
                    ConversationMessage.sequence.desc(),
                    ConversationMessage.created_at.desc(),
                )
            )
            rows = tuple(await session.scalars(statement))
        return _messages_from_turns(bounded_turns(rows, max_tokens))


def bounded_turns(
    rows: tuple[ConversationMessage, ...], max_tokens: int, *, max_turns: int | None = None
) -> tuple[ConversationTurn, ...]:
    turns = _group_turns(rows)
    if max_turns is not None:
        turns = turns[:max_turns]
    used = 0
    selected: list[ConversationTurn] = []
    for turn in turns:
        cost = _turn_tokens(turn)
        remaining = max_tokens - used
        if cost > remaining:
            if not selected and remaining > 0:
                selected.append(_truncate_turn(turn, remaining))
            break
        selected.append(turn)
        used += cost
    return tuple(reversed(selected))


def _messages_from_turns(
    turns: tuple[ConversationTurn, ...],
) -> tuple[ConversationHistoryMessage, ...]:
    messages: list[ConversationHistoryMessage] = []
    for turn in turns:
        messages.append(
            ConversationHistoryMessage("user", turn.user_content, turn.user_occurred_at)
        )
        if turn.assistant_content:
            messages.append(
                ConversationHistoryMessage(
                    "assistant", turn.assistant_content, turn.assistant_occurred_at
                )
            )
    return tuple(messages)


def _group_turns(rows: tuple[ConversationMessage, ...]) -> tuple[ConversationTurn, ...]:
    grouped: dict[str, list[tuple[ConversationMessage, str]]] = {}
    for row in rows:
        content = _clean(row.content)
        if not content:
            continue
        grouped.setdefault(row.interaction_id, []).append((row, content))
    turns: list[ConversationTurn] = []
    for interaction_id, messages in grouped.items():
        interaction_turns = _interaction_turns(interaction_id, messages)
        turns.extend(reversed(interaction_turns))
    return tuple(turns)


def _interaction_turns(
    interaction_id: str, messages: list[tuple[ConversationMessage, str]]
) -> list[ConversationTurn]:
    result: list[ConversationTurn] = []
    current: _TurnParts | None = None
    for row, content in sorted(messages, key=lambda item: _message_order(item[0])):
        if row.role == "assistant":
            if current is not None and current.assistant_content is None:
                current.assistant_content = content
                current.assistant_occurred_at = row.created_at
                result.append(_conversation_turn(interaction_id, current))
                current = None
            continue
        if current is not None:
            result.append(_conversation_turn(interaction_id, current))
        current = _TurnParts(user_content=content, user_occurred_at=row.created_at)
    if current is not None:
        result.append(_conversation_turn(interaction_id, current))
    return result


def _conversation_turn(interaction_id: str, parts: _TurnParts) -> ConversationTurn:
    if parts.user_content is None:
        raise ValueError("Conversation turn requires user content")
    return ConversationTurn(
        interaction_id=interaction_id,
        user_content=parts.user_content,
        user_occurred_at=parts.user_occurred_at,
        assistant_content=parts.assistant_content,
        assistant_occurred_at=parts.assistant_occurred_at,
    )


def _message_order(message: ConversationMessage) -> tuple[int, datetime]:
    return getattr(message, "sequence", 0), message.created_at


def _turn_tokens(turn: ConversationTurn) -> int:
    return _tokens(turn.user_content) + _tokens(turn.assistant_content or "")


def _truncate_turn(turn: ConversationTurn, max_tokens: int) -> ConversationTurn:
    user_tokens = _tokens(turn.user_content)
    user_budget = min(user_tokens, max_tokens)
    assistant_budget = max_tokens - user_budget
    return ConversationTurn(
        interaction_id=turn.interaction_id,
        user_content=_truncate_text(turn.user_content, user_budget),
        user_occurred_at=turn.user_occurred_at,
        assistant_content=(
            _truncate_text(turn.assistant_content, assistant_budget)
            if turn.assistant_content and assistant_budget > 0
            else None
        ),
        assistant_occurred_at=turn.assistant_occurred_at,
    )


@dataclass
class _TurnParts:
    user_content: str | None = None
    user_occurred_at: datetime | None = None
    assistant_content: str | None = None
    assistant_occurred_at: datetime | None = None


def _truncate_text(value: str, max_tokens: int) -> str:
    maximum = max(1, max_tokens * 4)
    return value if len(value) <= maximum else f"{value[: maximum - 1].rstrip()}…"


def _clean(value: str) -> str:
    return " ".join(_CONTROL_TAG_RE.sub("", value).split())


def _tokens(value: str) -> int:
    return max(1, (len(value) + 3) // 4)
