from __future__ import annotations

from typing import Protocol, cast

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.interactions.models import ConversationMessage


class MessageAccessContext(Protocol):
    @property
    def tenant_id(self) -> str: ...

    @property
    def agent_id(self) -> str: ...

    @property
    def actor_type(self) -> str: ...

    @property
    def actor_id(self) -> str: ...


async def search_messages(
    session: AsyncSession, context: MessageAccessContext, query: str, limit: int
) -> list[dict[str, object]]:
    rows = await session.scalars(
        visible_message_statement(context)
        .where(ConversationMessage.content.icontains(query, autoescape=True))
        .order_by(ConversationMessage.created_at.desc())
        .limit(limit)
    )
    return [message_view(item) for item in rows]


async def read_message(
    session: AsyncSession, context: MessageAccessContext, item_id: str
) -> dict[str, object] | None:
    item = await session.scalar(
        visible_message_statement(context).where(ConversationMessage.id == item_id)
    )
    return message_view(item, include_content=True) if item is not None else None


def source_types(value: object) -> tuple[str, ...]:
    if value is None:
        return ("memory",)
    if not isinstance(value, list):
        raise ValueError("sources is invalid")
    values = cast(list[object], value)
    sources = tuple(
        item for item in values if isinstance(item, str) and item in {"memory", "message"}
    )
    if not sources or len(sources) != len(values):
        raise ValueError("sources is invalid")
    return tuple(dict.fromkeys(sources))


def visible_message_statement(
    context: MessageAccessContext,
) -> Select[tuple[ConversationMessage]]:
    return select(ConversationMessage).where(
        ConversationMessage.tenant_id == context.tenant_id,
        ConversationMessage.agent_id == context.agent_id,
        ConversationMessage.actor_type == context.actor_type,
        ConversationMessage.actor_id == context.actor_id,
        ConversationMessage.status == "active",
    )


def message_view(item: ConversationMessage, *, include_content: bool = False) -> dict[str, object]:
    return {
        "item_type": "message",
        "id": item.id,
        "role": item.role,
        "conversation_id": item.conversation_id,
        "content": item.content if include_content else item.content[:1_000],
    }
