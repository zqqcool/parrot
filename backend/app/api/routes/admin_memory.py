from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session, require_permission
from app.core.request_id import get_request_id
from app.core.response import ApiResponse, ok
from app.modules.agents.catalog import AgentCatalog
from app.modules.iam.permissions import MEMORY_MANAGE, MEMORY_READ
from app.modules.iam.service import AuthenticatedSession
from app.modules.memory.schemas import (
    AgentMemorySearchPage,
    MemoryArchiveRequest,
    MemoryCreateRequest,
    MemoryUpdateRequest,
    MemoryView,
)
from app.modules.memory.service import MemoryService

router = APIRouter()


def _service(request: Request, session: AsyncSession) -> MemoryService:
    return MemoryService(
        session,
        request.app.state.database,
        AgentCatalog(session),
        request.app.state.memory_semantic_search,
        request.app.state.task_dispatcher,
    )


@router.get(
    "/tenants/{tenant_id}/memory/agent-view",
    response_model=ApiResponse[AgentMemorySearchPage],
)
async def search_agent_memory(
    tenant_id: str,
    request: Request,
    agent_id: str = Query(min_length=1, max_length=64),
    actor_id: str | None = Query(default=None, min_length=1, max_length=64),
    query: str | None = Query(default=None, max_length=300),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    authenticated: AuthenticatedSession = Depends(require_permission(MEMORY_READ)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[AgentMemorySearchPage]:
    data = await _service(request, session).search_agent_visible(
        authenticated.principal,
        tenant_id,
        agent_id=agent_id,
        actor_id=actor_id,
        query=query,
        offset=offset,
        limit=limit,
    )
    return ok(data, get_request_id(request))


@router.get("/tenants/{tenant_id}/memory", response_model=ApiResponse[list[MemoryView]])
async def list_memory(
    tenant_id: str,
    request: Request,
    query: str | None = Query(default=None, max_length=300),
    agent_id: str | None = None,
    record_status: str | None = Query(default=None, alias="status"),
    authenticated: AuthenticatedSession = Depends(require_permission(MEMORY_READ)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[list[MemoryView]]:
    data = await _service(request, session).list(
        authenticated.principal,
        tenant_id,
        query=query,
        agent_id=agent_id,
        record_status=record_status,
    )
    return ok(data, get_request_id(request))


@router.post("/tenants/{tenant_id}/memory", response_model=ApiResponse[MemoryView], status_code=201)
async def create_memory(
    tenant_id: str,
    payload: MemoryCreateRequest,
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_permission(MEMORY_MANAGE, csrf=True)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[MemoryView]:
    data = await _service(request, session).create(authenticated.principal, tenant_id, payload)
    return ok(data, get_request_id(request))


@router.put("/tenants/{tenant_id}/memory/{memory_id}", response_model=ApiResponse[MemoryView])
async def update_memory(
    tenant_id: str,
    memory_id: str,
    payload: MemoryUpdateRequest,
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_permission(MEMORY_MANAGE, csrf=True)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[MemoryView]:
    data = await _service(request, session).update(
        authenticated.principal, tenant_id, memory_id, payload
    )
    return ok(data, get_request_id(request))


@router.post(
    "/tenants/{tenant_id}/memory/{memory_id}/archive",
    response_model=ApiResponse[MemoryView],
)
async def archive_memory(
    tenant_id: str,
    memory_id: str,
    payload: MemoryArchiveRequest,
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_permission(MEMORY_MANAGE, csrf=True)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[MemoryView]:
    data = await _service(request, session).archive(
        authenticated.principal, tenant_id, memory_id, payload
    )
    return ok(data, get_request_id(request))
