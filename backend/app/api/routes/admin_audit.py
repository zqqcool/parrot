from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session, require_permission
from app.core.request_id import get_request_id
from app.core.response import ApiResponse, ok
from app.modules.audit.schemas import AuditView
from app.modules.audit.service import AuditQueryService
from app.modules.iam.permissions import AUDIT_READ
from app.modules.iam.service import AuthenticatedSession

router = APIRouter()


@router.get("/tenants/{tenant_id}/audit-logs", response_model=ApiResponse[list[AuditView]])
async def list_audit_logs(
    tenant_id: str,
    request: Request,
    query: str | None = Query(default=None, max_length=300),
    authenticated: AuthenticatedSession = Depends(require_permission(AUDIT_READ)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[list[AuditView]]:
    data = await AuditQueryService(session, request.app.state.database).list(
        authenticated.principal, tenant_id, query=query
    )
    return ok(data, get_request_id(request))
