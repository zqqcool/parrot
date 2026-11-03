from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session, require_permission
from app.core.request_id import get_request_id
from app.core.response import ApiResponse, ok
from app.modules.iam.permissions import (
    TENANT_GROUPS_MANAGE,
    TENANT_GROUPS_READ,
    TENANT_ROLES_MANAGE,
    TENANT_ROLES_READ,
)
from app.modules.iam.schemas import PermissionView, RoleCreateRequest, RoleView
from app.modules.iam.service import AuthenticatedSession
from app.modules.tenancy.access_service import AccessAssignmentService
from app.modules.tenancy.schemas import (
    AssignmentRequest,
    AssignmentView,
    GroupCreateRequest,
    GroupView,
)
from app.modules.tenancy.service import TenancyService

router = APIRouter()


@router.get("/tenants/{tenant_id}/groups", response_model=ApiResponse[list[GroupView]])
async def list_groups(
    tenant_id: str,
    request: Request,
    query: str | None = Query(default=None, max_length=300),
    authenticated: AuthenticatedSession = Depends(require_permission(TENANT_GROUPS_READ)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[list[GroupView]]:
    data = await _service(request, session).list_groups(
        authenticated.principal, tenant_id, query=query
    )
    return ok(data, get_request_id(request))


@router.post("/tenants/{tenant_id}/groups", response_model=ApiResponse[GroupView], status_code=201)
async def create_group(
    tenant_id: str,
    payload: GroupCreateRequest,
    request: Request,
    authenticated: AuthenticatedSession = Depends(
        require_permission(TENANT_GROUPS_MANAGE, csrf=True)
    ),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[GroupView]:
    data = await _service(request, session).create_group(
        authenticated.principal,
        tenant_id,
        payload,
    )
    return ok(data, get_request_id(request))


@router.put(
    "/tenants/{tenant_id}/groups/{group_id}/members",
    response_model=ApiResponse[dict[str, bool]],
)
async def replace_group_members(
    tenant_id: str,
    group_id: str,
    payload: AssignmentRequest,
    request: Request,
    authenticated: AuthenticatedSession = Depends(
        require_permission(TENANT_GROUPS_MANAGE, csrf=True)
    ),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[dict[str, bool]]:
    await _assignment_service(request, session).replace_group_members(
        authenticated.principal,
        tenant_id,
        group_id,
        payload.ids,
    )
    return ok({"updated": True}, get_request_id(request))


@router.get(
    "/tenants/{tenant_id}/groups/{group_id}/members",
    response_model=ApiResponse[AssignmentView],
)
async def get_group_members(
    tenant_id: str,
    group_id: str,
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_permission(TENANT_GROUPS_READ)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[AssignmentView]:
    ids = await _assignment_service(request, session).get_group_members(
        authenticated.principal, tenant_id, group_id
    )
    return ok(AssignmentView(ids=ids), get_request_id(request))


@router.put(
    "/tenants/{tenant_id}/groups/{group_id}/roles",
    response_model=ApiResponse[dict[str, bool]],
)
async def replace_group_roles(
    tenant_id: str,
    group_id: str,
    payload: AssignmentRequest,
    request: Request,
    authenticated: AuthenticatedSession = Depends(
        require_permission(TENANT_ROLES_MANAGE, csrf=True)
    ),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[dict[str, bool]]:
    await _assignment_service(request, session).replace_group_roles(
        authenticated.principal, tenant_id, group_id, payload.ids
    )
    return ok({"updated": True}, get_request_id(request))


@router.get(
    "/tenants/{tenant_id}/groups/{group_id}/roles",
    response_model=ApiResponse[AssignmentView],
)
async def get_group_roles(
    tenant_id: str,
    group_id: str,
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_permission(TENANT_ROLES_READ)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[AssignmentView]:
    ids = await _assignment_service(request, session).get_group_roles(
        authenticated.principal, tenant_id, group_id
    )
    return ok(AssignmentView(ids=ids), get_request_id(request))


@router.put(
    "/tenants/{tenant_id}/users/{user_id}/roles",
    response_model=ApiResponse[dict[str, bool]],
)
async def replace_user_roles(
    tenant_id: str,
    user_id: str,
    payload: AssignmentRequest,
    request: Request,
    authenticated: AuthenticatedSession = Depends(
        require_permission(TENANT_ROLES_MANAGE, csrf=True)
    ),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[dict[str, bool]]:
    await _assignment_service(request, session).replace_user_roles(
        authenticated.principal, tenant_id, user_id, payload.ids
    )
    return ok({"updated": True}, get_request_id(request))


@router.get(
    "/tenants/{tenant_id}/users/{user_id}/roles",
    response_model=ApiResponse[AssignmentView],
)
async def get_user_roles(
    tenant_id: str,
    user_id: str,
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_permission(TENANT_ROLES_READ)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[AssignmentView]:
    ids = await _assignment_service(request, session).get_user_roles(
        authenticated.principal, tenant_id, user_id
    )
    return ok(AssignmentView(ids=ids), get_request_id(request))


@router.get("/tenants/{tenant_id}/roles", response_model=ApiResponse[list[RoleView]])
async def list_roles(
    tenant_id: str,
    request: Request,
    query: str | None = Query(default=None, max_length=300),
    authenticated: AuthenticatedSession = Depends(require_permission(TENANT_ROLES_READ)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[list[RoleView]]:
    data = await _service(request, session).list_roles(
        authenticated.principal, tenant_id, query=query
    )
    return ok(data, get_request_id(request))


@router.post("/tenants/{tenant_id}/roles", response_model=ApiResponse[RoleView], status_code=201)
async def create_role(
    tenant_id: str,
    payload: RoleCreateRequest,
    request: Request,
    authenticated: AuthenticatedSession = Depends(
        require_permission(TENANT_ROLES_MANAGE, csrf=True)
    ),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[RoleView]:
    data = await _service(request, session).create_role(
        authenticated.principal,
        tenant_id,
        payload,
    )
    return ok(data, get_request_id(request))


@router.get("/permissions", response_model=ApiResponse[list[PermissionView]])
async def list_permissions(
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_permission(TENANT_ROLES_READ)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[list[PermissionView]]:
    data = await _service(request, session).list_permissions(authenticated.principal)
    return ok(data, get_request_id(request))


def _service(request: Request, session: AsyncSession) -> TenancyService:
    return TenancyService(session, request.app.state.database, request.app.state.settings)


def _assignment_service(request: Request, session: AsyncSession) -> AccessAssignmentService:
    return AccessAssignmentService(session, request.app.state.database)
