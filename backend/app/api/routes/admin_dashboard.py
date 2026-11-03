from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session, require_permission
from app.core.request_id import get_request_id
from app.core.response import ApiResponse, ok
from app.modules.dashboard.repository import DashboardRepository
from app.modules.dashboard.schemas import DashboardOverview
from app.modules.dashboard.service import DashboardService
from app.modules.iam.permissions import AGENTS_READ
from app.modules.iam.service import AuthenticatedSession

router = APIRouter()


@router.get(
    "/tenants/{tenant_id}/dashboard",
    response_model=ApiResponse[DashboardOverview],
)
async def get_dashboard(
    tenant_id: str,
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_permission(AGENTS_READ)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[DashboardOverview]:
    service = DashboardService(
        DashboardRepository(session),
        request.app.state.database,
        request.app.state.redis,
        request.app.state.settings,
    )
    data = await service.overview(authenticated.principal, tenant_id)
    return ok(data, get_request_id(request))
