from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import MemoryRuntimeSection
from app.core.ids import new_id
from app.core.task_dispatch import TaskDispatcher
from app.infrastructure.db.session import DatabaseManager
from app.modules.memory.automatic_context import AutomaticMemoryContextService
from app.modules.memory.context import MemoryContextItem, MemoryRecallContext, clean_text
from app.modules.memory.index_jobs import enqueue_memory_index
from app.modules.memory.message_search import read_message, search_messages, source_types
from app.modules.memory.models import MemoryRecord
from app.modules.memory.queries import visible_memory_statement
from app.modules.memory.retrieval import MemoryRetrievalService, SemanticMemorySearchPort
from app.modules.memory.runtime_contract import MEMORY_TYPES

logger = logging.getLogger(__name__)
_SECRET_RE = re.compile(
    r"(?:api[_-]?key|access[_-]?token|password|passwd|secret)\s*[:=]\s*\S+",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class MemoryRuntimeContext:
    tenant_id: str
    agent_id: str
    actor_type: str
    actor_id: str
    interaction_id: str
    conversation_id: str | None = None


class MemoryRuntimePort(Protocol):
    async def context_for(self, context: MemoryRuntimeContext) -> str: ...

    async def handle(
        self, context: MemoryRuntimeContext, arguments: dict[str, object]
    ) -> dict[str, object]: ...


@runtime_checkable
class AutomaticMemoryRuntimePort(Protocol):
    async def pinned_for(self, context: MemoryRuntimeContext) -> tuple[MemoryContextItem, ...]: ...

    async def recall_for(
        self, context: MemoryRuntimeContext, query: str
    ) -> MemoryRecallContext: ...


class SqlMemoryRuntime:
    """Tenant-isolated runtime memory with user confirmation for inferred writes."""

    def __init__(
        self,
        database: DatabaseManager,
        settings: MemoryRuntimeSection,
        semantic_search: SemanticMemorySearchPort | None = None,
        dispatcher: TaskDispatcher | None = None,
    ) -> None:
        self._database = database
        self._settings = settings
        self._semantic_search = semantic_search
        self._dispatcher = dispatcher
        self._automatic_context = AutomaticMemoryContextService(database, settings, semantic_search)

    async def context_for(self, context: MemoryRuntimeContext) -> str:
        items = await self.pinned_for(context)
        return self._automatic_context.render(items)

    async def pinned_for(self, context: MemoryRuntimeContext) -> tuple[MemoryContextItem, ...]:
        return await self._automatic_context.pinned_for(context)

    async def recall_for(self, context: MemoryRuntimeContext, query: str) -> MemoryRecallContext:
        return await self._automatic_context.recall_for(context, query)

    async def handle(
        self, context: MemoryRuntimeContext, arguments: dict[str, object]
    ) -> dict[str, object]:
        action = _text(arguments.get("action")).casefold()
        try:
            if action == "search":
                return await self._search(
                    context, _text(arguments.get("query")), source_types(arguments.get("sources"))
                )
            if action == "read":
                return await self._read(
                    context,
                    _text(arguments.get("item_id")) or _text(arguments.get("memory_id")),
                    _text(arguments.get("item_type")) or "memory",
                )
            if action == "add":
                return await self._add(context, arguments)
            if action == "replace":
                return await self._replace(context, arguments)
            if action == "delete":
                return await self._delete(context, arguments)
            if action in {"confirm", "reject"}:
                return await self._confirm(context, _text(arguments.get("memory_id")), action)
            return _error("MEMORY_ACTION_INVALID", "Memory action is unsupported")
        except ValueError as error:
            return _error("MEMORY_INPUT_INVALID", str(error))
        except Exception:
            logger.exception(
                "Runtime memory operation failed",
                extra={"tenant_id": context.tenant_id, "interaction_id": context.interaction_id},
            )
            return _error("MEMORY_UNAVAILABLE", "Memory is temporarily unavailable")

    async def _search(
        self, context: MemoryRuntimeContext, query: str, sources: tuple[str, ...]
    ) -> dict[str, object]:
        async with self._database.session() as session:
            await self._database.set_tenant(session, context.tenant_id)
            if query and "memory" in sources:
                result = await MemoryRetrievalService(
                    session,
                    self._semantic_search,
                    candidate_limit=min(self._settings.search_limit * 4, 100),
                ).retrieve(context, query)
                items = _window_item_views(result.records, self._settings.context_max_tokens)
                if "message" in sources:
                    items.extend(
                        await search_messages(session, context, query, self._settings.search_limit)
                    )
                return {
                    "status": "ok",
                    "items": items,
                    "count": len(items),
                    "anchor_id": result.anchor_id,
                    "retrieval_method": result.retrieval_method,
                    "degradation_reason": result.degradation_reason,
                }
            items = await self._browse_or_message_items(session, context, query, sources)
        return {"status": "ok", "items": items, "count": len(items), "retrieval_method": "browse"}

    async def _browse_or_message_items(
        self,
        session: AsyncSession,
        context: MemoryRuntimeContext,
        query: str,
        sources: tuple[str, ...],
    ) -> list[dict[str, object]]:
        items: list[dict[str, object]] = []
        if "memory" in sources:
            statement = _visible_statement(context, include_pending_owner=True)
            rows = await session.scalars(
                statement.order_by(MemoryRecord.updated_at.desc()).limit(
                    self._settings.search_limit
                )
            )
            items.extend(_item_view(item) for item in rows)
        if query and "message" in sources:
            items.extend(
                await search_messages(session, context, query, self._settings.search_limit)
            )
        return items[: self._settings.search_limit]

    async def _read(
        self, context: MemoryRuntimeContext, item_id: str, item_type: str
    ) -> dict[str, object]:
        if not item_id:
            raise ValueError("item_id is required")
        if item_type == "message":
            return await self._read_message(context, item_id)
        if item_type != "memory":
            raise ValueError("item_type is unsupported")
        async with self._database.session() as session:
            await self._database.set_tenant(session, context.tenant_id)
            item = await session.scalar(
                _visible_statement(context, include_pending_owner=True).where(
                    MemoryRecord.id == item_id
                )
            )
            if item is None:
                return _error("MEMORY_NOT_FOUND", "Memory is not available")
            return {"status": "ok", "item": _item_view(item, include_content=True)}

    async def _read_message(self, context: MemoryRuntimeContext, item_id: str) -> dict[str, object]:
        async with self._database.session() as session:
            await self._database.set_tenant(session, context.tenant_id)
            item = await read_message(session, context, item_id)
            if item is None:
                return _error("MEMORY_NOT_FOUND", "Message is not available")
            return {"status": "ok", "item": item}

    async def _add(
        self, context: MemoryRuntimeContext, arguments: dict[str, object]
    ) -> dict[str, object]:
        key = _required(arguments, "key", limit=191)
        content = _safe_content(
            _required(arguments, "content", limit=self._settings.max_content_chars)
        )
        memory_type = _required(arguments, "memory_type", limit=64)
        if memory_type not in MEMORY_TYPES:
            raise ValueError("memory_type is unsupported")
        scope_type, scope_id = _write_scope(context, _text(arguments.get("target")) or "user")
        intent = _text(arguments.get("write_intent")) or "inferred"
        if intent not in {"inferred", "explicit_user_request"}:
            raise ValueError("write_intent is invalid")
        pending = intent == "inferred"
        async with self._database.session() as session:
            await self._database.set_tenant(session, context.tenant_id)
            item = MemoryRecord(
                id=new_id("memory"),
                tenant_id=context.tenant_id,
                agent_id=context.agent_id,
                scope_type=scope_type,
                scope_id=scope_id,
                key=key,
                content=content,
                memory_type=memory_type,
                retention_policy="pending_confirmation" if pending else "user_managed",
                status="pending_confirmation" if pending else "active",
                created_by_user_id=context.actor_id,
                source_type="agent_tool",
                write_intent=intent,
                requires_confirmation=pending,
                sensitivity_level="standard",
                conversation_id=context.conversation_id,
            )
            session.add(item)
            await session.flush()
            await enqueue_memory_index(session, item, action="index", dispatcher=self._dispatcher)
            return {
                "status": "ok",
                "item": _item_view(item, include_content=True),
                "must_confirm": pending,
            }

    async def _replace(
        self, context: MemoryRuntimeContext, arguments: dict[str, object]
    ) -> dict[str, object]:
        async with self._database.session() as session:
            item = await self._owned_item(
                session, context, _required(arguments, "memory_id", limit=64)
            )
            if item.version != _version(arguments):
                return _error("MEMORY_VERSION_CONFLICT", "Memory changed; refresh before replacing")
            item.content = _safe_content(
                _required(arguments, "content", limit=self._settings.max_content_chars)
            )
            item.version += 1
            await session.flush()
            await enqueue_memory_index(session, item, action="index", dispatcher=self._dispatcher)
            return {"status": "ok", "item": _item_view(item, include_content=True)}

    async def _delete(
        self, context: MemoryRuntimeContext, arguments: dict[str, object]
    ) -> dict[str, object]:
        async with self._database.session() as session:
            item = await self._owned_item(
                session, context, _required(arguments, "memory_id", limit=64)
            )
            if item.version != _version(arguments):
                return _error("MEMORY_VERSION_CONFLICT", "Memory changed; refresh before deleting")
            item.status = "archived"
            item.version += 1
            await session.flush()
            await enqueue_memory_index(session, item, action="delete", dispatcher=self._dispatcher)
            return {"status": "ok", "item": _item_view(item)}

    async def _confirm(
        self, context: MemoryRuntimeContext, memory_id: str, action: str
    ) -> dict[str, object]:
        async with self._database.session() as session:
            item = await self._owned_item(session, context, memory_id)
            if action == "confirm":
                item.status = "active"
                item.requires_confirmation = False
                item.retention_policy = "user_managed"
            else:
                item.status = "archived"
            item.version += 1
            await session.flush()
            await enqueue_memory_index(
                session,
                item,
                action="index" if action == "confirm" else "delete",
                dispatcher=self._dispatcher,
            )
            return {"status": "ok", "item": _item_view(item), "must_confirm": False}

    async def _owned_item(
        self, session: AsyncSession, context: MemoryRuntimeContext, memory_id: str
    ) -> MemoryRecord:
        if not memory_id:
            raise ValueError("memory_id is required")
        await self._database.set_tenant(session, context.tenant_id)
        item = await session.scalar(
            select(MemoryRecord).where(
                MemoryRecord.tenant_id == context.tenant_id,
                MemoryRecord.id == memory_id,
                MemoryRecord.created_by_user_id == context.actor_id,
                MemoryRecord.agent_id == context.agent_id,
                MemoryRecord.status.not_in(("archived", "deleted")),
            )
        )
        if item is None:
            raise ValueError("memory is not available")
        return item


def _visible_statement(
    context: MemoryRuntimeContext, *, include_pending_owner: bool
) -> Select[tuple[MemoryRecord]]:
    return visible_memory_statement(
        tenant_id=context.tenant_id,
        agent_id=context.agent_id,
        actor_id=context.actor_id,
        conversation_id=context.conversation_id,
        include_pending_owner=include_pending_owner,
    )


def _item_view(
    item: MemoryRecord, *, include_content: bool = False, semantic_match: bool = False
) -> dict[str, object]:
    result: dict[str, object] = {
        "item_type": "memory",
        "id": item.id,
        "key": item.key,
        "scope_type": item.scope_type,
        "memory_type": item.memory_type,
        "status": item.status,
        "version": item.version,
        "requires_confirmation": item.requires_confirmation,
        "semantic_match": semantic_match,
    }
    if include_content:
        result["content"] = item.content
    return result


def _window_item_views(items: tuple[MemoryRecord, ...], max_tokens: int) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    remaining = max_tokens
    for item in items:
        content = clean_text(item.content)
        cost = max(1, (len(content) + 3) // 4)
        if result and cost > remaining:
            continue
        visible = content[: max(1, remaining * 4)].rstrip()
        result.append(_item_view(item, include_content=True) | {"content": visible})
        remaining -= min(cost, remaining)
        if remaining <= 0:
            break
    return result


def _write_scope(context: MemoryRuntimeContext, target: str) -> tuple[str, str]:
    values = {
        "user": ("user", context.actor_id),
        "agent": ("agent", context.agent_id),
        "conversation": ("conversation", context.conversation_id),
    }
    scope = values.get(target)
    if scope is None or not scope[1]:
        raise ValueError("memory target is unavailable in this interaction")
    return scope[0], scope[1]


def _safe_content(value: str) -> str:
    if _SECRET_RE.search(value):
        raise ValueError("memory content appears to contain a secret")
    return clean_text(value)


def _required(arguments: dict[str, object], key: str, *, limit: int) -> str:
    value = _text(arguments.get(key))
    if not value:
        raise ValueError(f"{key} is required")
    if len(value) > limit:
        raise ValueError(f"{key} exceeds the allowed length")
    return value


def _version(arguments: dict[str, object]) -> int:
    value = arguments.get("expected_version")
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError("expected_version is required")
    return value


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _error(code: str, message: str) -> dict[str, object]:
    return {"status": "rejected", "code": code, "message": message}
