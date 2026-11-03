from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.errors import AppError
from app.core.ids import new_id
from app.core.task_dispatch import TaskDispatcher
from app.infrastructure.db.session import DatabaseManager
from app.modules.agents.ports import AgentCatalogPort
from app.modules.audit.service import append_audit
from app.modules.iam.permissions import PLATFORM_TENANTS_MANAGE
from app.modules.iam.schemas import PrincipalContext, UserReference
from app.modules.iam.user_references import UserReferenceResolver
from app.modules.memory.index_jobs import enqueue_memory_index
from app.modules.memory.models import MemoryRecord
from app.modules.memory.queries import visible_memory_statement
from app.modules.memory.retrieval import MemoryRetrievalService, SemanticMemorySearchPort
from app.modules.memory.schemas import (
    AgentMemorySearchPage,
    MemoryArchiveRequest,
    MemoryCreateRequest,
    MemoryUpdateRequest,
    MemoryView,
)


@dataclass(frozen=True)
class _AgentViewContext:
    tenant_id: str
    agent_id: str
    actor_id: str | None
    conversation_id: str | None = None


class MemoryService:
    def __init__(
        self,
        session: AsyncSession,
        database: DatabaseManager,
        agents: AgentCatalogPort,
        semantic_search: SemanticMemorySearchPort | None = None,
        dispatcher: TaskDispatcher | None = None,
    ) -> None:
        self.session = session
        self.database = database
        self.agents = agents
        self.semantic_search = semantic_search
        self.dispatcher = dispatcher

    async def list(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        *,
        query: str | None,
        agent_id: str | None,
        record_status: str | None,
    ) -> list[MemoryView]:
        await self._enter(principal, tenant_id, "memory.read")
        statement = select(MemoryRecord).where(MemoryRecord.tenant_id == tenant_id)
        if agent_id:
            statement = statement.where(MemoryRecord.agent_id == agent_id)
        if record_status:
            statement = statement.where(MemoryRecord.status == record_status)
        else:
            statement = statement.where(MemoryRecord.status.not_in(("archived", "deleted")))
        normalized = query.strip() if query else ""
        if normalized:
            statement = statement.where(
                or_(
                    MemoryRecord.key.icontains(normalized, autoescape=True),
                    MemoryRecord.content.icontains(normalized, autoescape=True),
                    MemoryRecord.scope_id.icontains(normalized, autoescape=True),
                )
            )
        rows = await self.session.scalars(statement.order_by(MemoryRecord.updated_at.desc()))
        return await self._views(list(rows))

    async def search_agent_visible(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        *,
        agent_id: str,
        actor_id: str | None,
        query: str | None,
        offset: int,
        limit: int,
    ) -> AgentMemorySearchPage:
        await self._enter(principal, tenant_id, "memory.read")
        await self._validate_agent(tenant_id, agent_id)
        await self._validate_actor(tenant_id, actor_id)
        statement = visible_memory_statement(
            tenant_id=tenant_id,
            agent_id=agent_id,
            actor_id=actor_id,
            include_pending_owner=True,
        )
        normalized = query.strip() if query else ""
        if normalized:
            result = await MemoryRetrievalService(
                self.session,
                self.semantic_search,
                candidate_limit=min(limit * 4, 100),
            ).retrieve(_AgentViewContext(tenant_id, agent_id, actor_id), normalized)
            return AgentMemorySearchPage(
                items=await self._views(list(result.records)),
                total=len(result.records),
                offset=0,
                limit=limit,
                mode="window",
                anchor_id=result.anchor_id,
                retrieval_method=result.retrieval_method,
                degradation_reason=result.degradation_reason,
            )
        total = await self.session.scalar(select(func.count()).select_from(statement.subquery()))
        rows = await self.session.scalars(
            statement.order_by(MemoryRecord.updated_at.desc()).offset(offset).limit(limit)
        )
        return AgentMemorySearchPage(
            items=await self._views(list(rows)),
            total=int(total or 0),
            offset=offset,
            limit=limit,
            mode="browse",
            retrieval_method="browse",
        )

    async def create(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        payload: MemoryCreateRequest,
    ) -> MemoryView:
        await self._enter(principal, tenant_id, "memory.manage")
        await self._validate_agent(tenant_id, payload.agent_id)
        if payload.scope_type == "agent" and payload.scope_id != payload.agent_id:
            raise AppError(
                "MEMORY_SCOPE_INVALID",
                "Agent memory scope must match agent_id",
                status.HTTP_422_UNPROCESSABLE_CONTENT,
            )
        model = MemoryRecord(
            id=new_id("memory"),
            tenant_id=tenant_id,
            created_by_user_id=principal.subject_id,
            **payload.model_dump(),
        )
        try:
            async with self.session.begin_nested():
                self.session.add(model)
                await self.session.flush()
                await enqueue_memory_index(
                    self.session, model, action="index", dispatcher=self.dispatcher
                )
        except IntegrityError as exc:
            raise AppError(
                "MEMORY_ALREADY_EXISTS",
                "A memory with this scope and key already exists",
                status.HTTP_409_CONFLICT,
            ) from exc
        append_audit(
            self.session, principal, "memory.create", "memory", model.id, tenant_id=tenant_id
        )
        return await self._view(model)

    async def update(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        memory_id: str,
        payload: MemoryUpdateRequest,
    ) -> MemoryView:
        await self._enter(principal, tenant_id, "memory.manage")
        model = await self._get(tenant_id, memory_id)
        if model.status != "active":
            raise AppError("MEMORY_ARCHIVED", "Memory is archived", status.HTTP_409_CONFLICT)
        await self._optimistic_update(
            tenant_id,
            memory_id,
            payload.expected_version,
            {"content": payload.content},
        )
        await self.session.refresh(model)
        await enqueue_memory_index(self.session, model, action="index", dispatcher=self.dispatcher)
        append_audit(
            self.session,
            principal,
            "memory.update",
            "memory",
            model.id,
            {"version": model.version},
            tenant_id=tenant_id,
        )
        return await self._view(model)

    async def archive(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        memory_id: str,
        payload: MemoryArchiveRequest,
    ) -> MemoryView:
        await self._enter(principal, tenant_id, "memory.manage")
        model = await self._get(tenant_id, memory_id)
        await self._optimistic_update(
            tenant_id, memory_id, payload.expected_version, {"status": "archived"}
        )
        await self.session.refresh(model)
        await enqueue_memory_index(self.session, model, action="delete", dispatcher=self.dispatcher)
        append_audit(
            self.session, principal, "memory.archive", "memory", model.id, tenant_id=tenant_id
        )
        return await self._view(model)

    async def _optimistic_update(
        self, tenant_id: str, memory_id: str, version: int, values: dict[str, object]
    ) -> None:
        result = await self.session.execute(
            update(MemoryRecord)
            .where(
                MemoryRecord.tenant_id == tenant_id,
                MemoryRecord.id == memory_id,
                MemoryRecord.version == version,
            )
            .values(**values, version=version + 1)
            .returning(MemoryRecord.id)
        )
        if result.scalar_one_or_none() is None:
            raise AppError(
                "MEMORY_VERSION_CONFLICT",
                "Memory was changed by another request",
                status.HTTP_409_CONFLICT,
            )

    async def _get(self, tenant_id: str, memory_id: str) -> MemoryRecord:
        model = await self.session.scalar(
            select(MemoryRecord).where(
                MemoryRecord.tenant_id == tenant_id, MemoryRecord.id == memory_id
            )
        )
        if model is None:
            raise AppError("RESOURCE_NOT_FOUND", "Memory not found", status.HTTP_404_NOT_FOUND)
        return model

    async def _validate_agent(self, tenant_id: str, agent_id: str | None) -> None:
        if not agent_id:
            return
        if not await self.agents.exists(tenant_id, agent_id):
            raise AppError("RESOURCE_NOT_FOUND", "Agent not found", status.HTTP_404_NOT_FOUND)

    async def _validate_actor(self, tenant_id: str, actor_id: str | None) -> None:
        if not actor_id:
            return
        users = await UserReferenceResolver(self.session).resolve(tenant_id, (actor_id,))
        if actor_id not in users:
            raise AppError("RESOURCE_NOT_FOUND", "User not found", status.HTTP_404_NOT_FOUND)

    async def _enter(self, principal: PrincipalContext, tenant_id: str, permission: str) -> None:
        if (
            principal.tenant_id != tenant_id
            and PLATFORM_TENANTS_MANAGE not in principal.permissions
        ):
            raise AppError("RESOURCE_NOT_FOUND", "Memory not found", status.HTTP_404_NOT_FOUND)
        if permission not in principal.permissions:
            raise AppError("FORBIDDEN", "Permission denied", status.HTTP_403_FORBIDDEN)
        await self.database.set_tenant(self.session, tenant_id)

    async def _view(self, item: MemoryRecord) -> MemoryView:
        users = await UserReferenceResolver(self.session).resolve(
            item.tenant_id, (item.created_by_user_id,)
        )
        agent_names = (
            await self.agents.names(item.tenant_id, (item.agent_id,)) if item.agent_id else {}
        )
        return self.view(item, users, agent_names)

    async def _views(self, items: list[MemoryRecord]) -> list[MemoryView]:
        tenant_id = items[0].tenant_id if items else None
        users = await UserReferenceResolver(self.session).resolve(
            tenant_id, (item.created_by_user_id for item in items)
        )
        agent_ids = tuple(dict.fromkeys(item.agent_id for item in items if item.agent_id))
        agent_names = await self.agents.names(tenant_id, agent_ids) if tenant_id else {}
        return [self.view(item, users, agent_names) for item in items]

    @staticmethod
    def view(
        item: MemoryRecord,
        users: Mapping[str, UserReference] | None = None,
        agent_names: Mapping[str, str] | None = None,
    ) -> MemoryView:
        view = MemoryView.model_validate(item, from_attributes=True)
        return view.model_copy(
            update={
                "agent_name": (agent_names or {}).get(item.agent_id or ""),
                "created_by": (users or {}).get(item.created_by_user_id),
            }
        )
