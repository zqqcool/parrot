from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.avatar_response import avatar_response
from app.api.dependencies import get_db_session, require_permission
from app.core.request_id import get_request_id
from app.core.response import ApiResponse, ok
from app.modules.iam.permissions import TENANT_USERS_MANAGE, TENANT_USERS_READ
from app.modules.iam.schemas import (
    PasswordResetRequest,
    UserAvatarAttachRequest,
    UserAvatarUploadGrantView,
    UserAvatarUploadRequest,
    UserCreateRequest,
    UserUpdateRequest,
    UserView,
)
from app.modules.iam.service import AuthenticatedSession
from app.modules.tenancy.service import TenancyService
from app.modules.tenancy.user_avatar_service import TenantUserAvatarService

router = APIRouter()


@router.get("/tenants/{tenant_id}/users", response_model=ApiResponse[list[UserView]])
async def list_users(
    tenant_id: str,
    request: Request,
    query: str | None = Query(default=None, max_length=300),
    authenticated: AuthenticatedSession = Depends(require_permission(TENANT_USERS_READ)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[list[UserView]]:
    data = await _service(request, session).list_users(
        authenticated.principal, tenant_id, query=query
    )
    return ok(data, get_request_id(request))


@router.post(
    "/tenants/{tenant_id}/users",
    response_model=ApiResponse[UserView],
    status_code=201,
)
async def create_user(
    tenant_id: str,
    payload: UserCreateRequest,
    request: Request,
    authenticated: AuthenticatedSession = Depends(
        require_permission(TENANT_USERS_MANAGE, csrf=True)
    ),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[UserView]:
    data = await _service(request, session).create_user(
        authenticated.principal,
        tenant_id,
        payload,
    )
    return ok(data, get_request_id(request))


@router.patch("/tenants/{tenant_id}/users/{user_id}", response_model=ApiResponse[UserView])
async def update_user(
    tenant_id: str,
    user_id: str,
    payload: UserUpdateRequest,
    request: Request,
    authenticated: AuthenticatedSession = Depends(
        require_permission(TENANT_USERS_MANAGE, csrf=True)
    ),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[UserView]:
    data = await _service(request, session).update_user(
        authenticated.principal,
        tenant_id,
        user_id,
        payload,
    )
    return ok(data, get_request_id(request))


@router.post(
    "/tenants/{tenant_id}/users/{user_id}/password-reset",
    response_model=ApiResponse[dict[str, bool]],
)
async def reset_password(
    tenant_id: str,
    user_id: str,
    payload: PasswordResetRequest,
    request: Request,
    authenticated: AuthenticatedSession = Depends(
        require_permission(TENANT_USERS_MANAGE, csrf=True)
    ),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[dict[str, bool]]:
    await _service(request, session).reset_password(
        authenticated.principal,
        tenant_id,
        user_id,
        payload.temporary_password,
    )
    return ok({"reset": True}, get_request_id(request))


@router.post(
    "/tenants/{tenant_id}/users/{user_id}/avatar-upload-grant",
    response_model=ApiResponse[UserAvatarUploadGrantView],
)
async def issue_user_avatar_upload(
    tenant_id: str,
    user_id: str,
    payload: UserAvatarUploadRequest,
    request: Request,
    authenticated: AuthenticatedSession = Depends(
        require_permission(TENANT_USERS_MANAGE, csrf=True)
    ),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[UserAvatarUploadGrantView]:
    grant = await _avatar_service(request, session).issue_upload(
        authenticated.principal,
        tenant_id,
        user_id,
        payload.content_type,
        payload.size_bytes,
    )
    return ok(
        UserAvatarUploadGrantView(
            object_key=grant.object_key,
            upload_key=grant.upload_key,
            upload_token=grant.upload_token,
            expires_at=grant.expires_at,
        ),
        get_request_id(request),
    )


@router.put(
    "/tenants/{tenant_id}/users/{user_id}/avatar",
    response_model=ApiResponse[dict[str, bool]],
)
async def attach_user_avatar(
    tenant_id: str,
    user_id: str,
    payload: UserAvatarAttachRequest,
    request: Request,
    authenticated: AuthenticatedSession = Depends(
        require_permission(TENANT_USERS_MANAGE, csrf=True)
    ),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[dict[str, bool]]:
    attached = await _avatar_service(request, session).attach(
        authenticated.principal,
        tenant_id,
        user_id,
        payload.object_key,
    )
    return ok({"attached": attached}, get_request_id(request))


@router.get("/tenants/{tenant_id}/users/{user_id}/avatar", response_class=Response)
async def get_user_avatar(
    tenant_id: str,
    user_id: str,
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_permission(TENANT_USERS_READ)),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    content, content_type = await _avatar_service(request, session).get(
        authenticated.principal,
        tenant_id,
        user_id,
    )
    return avatar_response(content, content_type)


def _service(request: Request, session: AsyncSession) -> TenancyService:
    return TenancyService(session, request.app.state.database, request.app.state.settings)


def _avatar_service(request: Request, session: AsyncSession) -> TenantUserAvatarService:
    return TenantUserAvatarService(
        session,
        request.app.state.database,
        request.app.state.object_storage,
        request.app.state.settings.media.max_user_avatar_bytes,
    )
