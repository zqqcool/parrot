from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session, require_permission
from app.core.request_id import get_request_id
from app.core.response import ApiResponse, ok
from app.modules.iam.permissions import PLATFORM_TENANTS_MANAGE
from app.modules.iam.service import AuthenticatedSession
from app.modules.tenancy.schemas import TenantCreateRequest, TenantView
from app.modules.tenancy.service import TenancyService

router = APIRouter()


@router.get("/tenants", response_model=ApiResponse[list[TenantView]])
async def list_tenants(
    request: Request,
    query: str | None = Query(default=None, max_length=300),
    authenticated: AuthenticatedSession = Depends(require_permission(PLATFORM_TENANTS_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[list[TenantView]]:
    data = await _service(request, session).list_tenants(authenticated.principal, query=query)
    return ok(data, get_request_id(request))


@router.post("/tenants", response_model=ApiResponse[TenantView], status_code=201)
async def create_tenant(
    payload: TenantCreateRequest,
    request: Request,
    authenticated: AuthenticatedSession = Depends(
        require_permission(PLATFORM_TENANTS_MANAGE, csrf=True)
    ),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[TenantView]:
    data = await _service(request, session).create_tenant(authenticated.principal, payload)
    return ok(data, get_request_id(request))


def _service(request: Request, session: AsyncSession) -> TenancyService:
    return TenancyService(session, request.app.state.database, request.app.state.settings)
