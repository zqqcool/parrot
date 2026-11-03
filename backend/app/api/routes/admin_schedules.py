from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session, require_permission
from app.core.request_id import get_request_id
from app.core.response import ApiResponse, ok
from app.modules.agents.catalog import AgentCatalog
from app.modules.iam.permissions import SCHEDULES_MANAGE, SCHEDULES_READ
from app.modules.iam.service import AuthenticatedSession
from app.modules.interactions.runtime_factory import build_profile_resolver
from app.modules.schedules.schemas import (
    ScheduleCreateRequest,
    ScheduleExecutionView,
    ScheduleUpdateRequest,
    ScheduleView,
)
from app.modules.schedules.service import ScheduleService

router = APIRouter()


def _service(request: Request, session: AsyncSession) -> ScheduleService:
    return ScheduleService(
        session,
        request.app.state.database,
        request.app.state.runtime,
        AgentCatalog(session),
        request.app.state.settings.schedules.default_timezone,
        request.app.state.redis,
        build_profile_resolver(request.app.state.settings, session),
        request.app.state.task_dispatcher,
    )


@router.get("/tenants/{tenant_id}/schedules", response_model=ApiResponse[list[ScheduleView]])
async def list_schedules(
    tenant_id: str,
    request: Request,
    task_status: str | None = Query(default=None, alias="status"),
    query: str | None = Query(default=None, max_length=300),
    authenticated: AuthenticatedSession = Depends(require_permission(SCHEDULES_READ)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[list[ScheduleView]]:
    data = await _service(request, session).list(
        authenticated.principal, tenant_id, task_status, query=query
    )
    return ok(data, get_request_id(request))


@router.post(
    "/tenants/{tenant_id}/schedules",
    response_model=ApiResponse[ScheduleView],
    status_code=201,
)
async def create_schedule(
    tenant_id: str,
    payload: ScheduleCreateRequest,
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_permission(SCHEDULES_MANAGE, csrf=True)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[ScheduleView]:
    data = await _service(request, session).create(authenticated.principal, tenant_id, payload)
    return ok(data, get_request_id(request))


@router.put(
    "/tenants/{tenant_id}/schedules/{schedule_id}", response_model=ApiResponse[ScheduleView]
)
async def update_schedule(
    tenant_id: str,
    schedule_id: str,
    payload: ScheduleUpdateRequest,
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_permission(SCHEDULES_MANAGE, csrf=True)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[ScheduleView]:
    data = await _service(request, session).update(
        authenticated.principal, tenant_id, schedule_id, payload
    )
    return ok(data, get_request_id(request))


@router.post(
    "/tenants/{tenant_id}/schedules/{schedule_id}/enable",
    response_model=ApiResponse[ScheduleView],
)
async def enable_schedule(
    tenant_id: str,
    schedule_id: str,
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_permission(SCHEDULES_MANAGE, csrf=True)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[ScheduleView]:
    data = await _service(request, session).set_enabled(
        authenticated.principal, tenant_id, schedule_id, True
    )
    return ok(data, get_request_id(request))


@router.post(
    "/tenants/{tenant_id}/schedules/{schedule_id}/disable",
    response_model=ApiResponse[ScheduleView],
)
async def disable_schedule(
    tenant_id: str,
    schedule_id: str,
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_permission(SCHEDULES_MANAGE, csrf=True)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[ScheduleView]:
    data = await _service(request, session).set_enabled(
        authenticated.principal, tenant_id, schedule_id, False
    )
    return ok(data, get_request_id(request))


@router.post(
    "/tenants/{tenant_id}/schedules/{schedule_id}/run-now",
    response_model=ApiResponse[ScheduleExecutionView],
)
async def run_schedule_now(
    tenant_id: str,
    schedule_id: str,
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_permission(SCHEDULES_MANAGE, csrf=True)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[ScheduleExecutionView]:
    data = await _service(request, session).run_now(authenticated.principal, tenant_id, schedule_id)
    return ok(data, get_request_id(request))


@router.get(
    "/tenants/{tenant_id}/schedules/{schedule_id}/executions",
    response_model=ApiResponse[list[ScheduleExecutionView]],
)
async def list_schedule_executions(
    tenant_id: str,
    schedule_id: str,
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_permission(SCHEDULES_READ)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[list[ScheduleExecutionView]]:
    data = await _service(request, session).executions(
        authenticated.principal, tenant_id, schedule_id
    )
    return ok(data, get_request_id(request))
