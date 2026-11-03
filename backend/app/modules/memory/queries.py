from __future__ import annotations

from sqlalchemy import ColumnElement, Select, or_, select

from app.core.clock import utc_now
from app.modules.memory.models import MemoryRecord


def visible_memory_statement(
    *,
    tenant_id: str,
    agent_id: str,
    actor_id: str | None,
    conversation_id: str | None = None,
    include_pending_owner: bool,
) -> Select[tuple[MemoryRecord]]:
    """Return memory visible to one concrete Agent runtime context."""
    scope_filters = [
        MemoryRecord.scope_type == "tenant",
        (MemoryRecord.scope_type == "agent") & (MemoryRecord.scope_id == agent_id),
    ]
    if actor_id:
        scope_filters.append(
            (MemoryRecord.scope_type == "user") & (MemoryRecord.scope_id == actor_id)
        )
    if conversation_id:
        scope_filters.append(
            (MemoryRecord.scope_type == "conversation") & (MemoryRecord.scope_id == conversation_id)
        )
    confirmation = MemoryRecord.requires_confirmation.is_(False)
    if include_pending_owner and actor_id:
        confirmation = or_(confirmation, MemoryRecord.created_by_user_id == actor_id)
    return select(MemoryRecord).where(
        MemoryRecord.tenant_id == tenant_id,
        MemoryRecord.status.not_in(("archived", "deleted")),
        or_(MemoryRecord.expires_at.is_(None), MemoryRecord.expires_at > utc_now()),
        or_(MemoryRecord.agent_id.is_(None), MemoryRecord.agent_id == agent_id),
        or_(*scope_filters),
        confirmation,
    )


def memory_text_match(query: str) -> ColumnElement[bool]:
    """Build the shared lexical match used by the runtime and management plane."""
    return or_(
        MemoryRecord.key.icontains(query, autoescape=True),
        MemoryRecord.content.icontains(query, autoescape=True),
    )
