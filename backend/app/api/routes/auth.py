from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.api.avatar_response import avatar_response
from app.api.dependencies import (
    get_authenticated_session,
    get_db_session,
    verify_origin,
)
from app.core.config import AppConfig
from app.core.errors import AppError
from app.core.object_storage import ObjectUploadGrant
from app.core.request_id import get_request_id
from app.core.response import ApiResponse, ok
from app.infrastructure.redis import RedisManager
from app.modules.iam.profile_service import CurrentUserProfileService
from app.modules.iam.schemas import (
    CurrentUserProfileUpdateRequest,
    LoginRequest,
    PasswordChangeRequest,
    SessionData,
    TenantSwitchRequest,
    UserAvatarAttachRequest,
    UserAvatarUploadGrantView,
    UserAvatarUploadRequest,
)
from app.modules.iam.service import AuthenticatedSession, SessionService, normalize_username
from app.modules.tenancy.user_avatar_service import TenantUserAvatarService

router = APIRouter()


@router.post("/login", response_model=ApiResponse[SessionData])
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    origin: str | None = Header(default=None, alias="Origin"),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[SessionData]:
    settings: AppConfig = request.app.state.settings
    verify_origin(settings, origin)
    await _check_login_rate_limit(request, payload.username)
    created = await SessionService(session, settings, request.app.state.database).login(
        payload.username,
        payload.password,
        get_request_id(request),
        request.headers.get("User-Agent"),
    )
    _set_session_cookie(response, settings, created.raw_token)
    return ok(created.data, get_request_id(request))


@router.get("/session", response_model=ApiResponse[SessionData])
async def read_session(
    request: Request,
    authenticated: AuthenticatedSession = Depends(get_authenticated_session),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[SessionData]:
    data = await SessionService(
        session, request.app.state.settings, request.app.state.database
    ).session_data(authenticated)
    return ok(data, get_request_id(request))


@router.patch("/profile", response_model=ApiResponse[dict[str, bool]])
async def update_current_user_profile(
    payload: CurrentUserProfileUpdateRequest,
    request: Request,
    authenticated: AuthenticatedSession = Depends(get_authenticated_session),
    session: AsyncSession = Depends(get_db_session),
    csrf_header: str | None = Header(default=None, alias="X-CSRF-Token"),
    origin: str | None = Header(default=None, alias="Origin"),
) -> ApiResponse[dict[str, bool]]:
    _csrf_service(request, session, authenticated, csrf_header, origin)
    await CurrentUserProfileService(session).update_display_name(
        authenticated.principal, payload.display_name
    )
    return ok({"updated": True}, get_request_id(request))


@router.post(
    "/profile/avatar-upload-grant",
    response_model=ApiResponse[UserAvatarUploadGrantView],
)
async def issue_current_user_avatar_upload(
    payload: UserAvatarUploadRequest,
    request: Request,
    authenticated: AuthenticatedSession = Depends(get_authenticated_session),
    session: AsyncSession = Depends(get_db_session),
    csrf_header: str | None = Header(default=None, alias="X-CSRF-Token"),
    origin: str | None = Header(default=None, alias="Origin"),
) -> ApiResponse[UserAvatarUploadGrantView]:
    _csrf_service(request, session, authenticated, csrf_header, origin)
    grant = await _avatar_service(request, session).issue_self_upload(
        authenticated.principal,
        payload.content_type,
        payload.size_bytes,
    )
    return ok(_upload_grant_view(grant), get_request_id(request))


@router.put("/profile/avatar", response_model=ApiResponse[dict[str, bool]])
async def attach_current_user_avatar(
    payload: UserAvatarAttachRequest,
    request: Request,
    authenticated: AuthenticatedSession = Depends(get_authenticated_session),
    session: AsyncSession = Depends(get_db_session),
    csrf_header: str | None = Header(default=None, alias="X-CSRF-Token"),
    origin: str | None = Header(default=None, alias="Origin"),
) -> ApiResponse[dict[str, bool]]:
    _csrf_service(request, session, authenticated, csrf_header, origin)
    attached = await _avatar_service(request, session).attach_self(
        authenticated.principal, payload.object_key
    )
    return ok({"attached": attached}, get_request_id(request))


@router.get("/profile/avatar", response_class=Response)
async def get_current_user_avatar(
    request: Request,
    authenticated: AuthenticatedSession = Depends(get_authenticated_session),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    content, content_type = await _avatar_service(request, session).get_self(
        authenticated.principal
    )
    return avatar_response(content, content_type)


@router.post("/logout", response_model=ApiResponse[dict[str, bool]])
async def logout(
    request: Request,
    response: Response,
    authenticated: AuthenticatedSession = Depends(get_authenticated_session),
    session: AsyncSession = Depends(get_db_session),
    csrf_header: str | None = Header(default=None, alias="X-CSRF-Token"),
    origin: str | None = Header(default=None, alias="Origin"),
) -> ApiResponse[dict[str, bool]]:
    service = _csrf_service(request, session, authenticated, csrf_header, origin)
    await service.logout(authenticated)
    _delete_session_cookie(response, request.app.state.settings)
    return ok({"revoked": True}, get_request_id(request))


@router.post("/password", response_model=ApiResponse[dict[str, bool]])
async def change_password(
    payload: PasswordChangeRequest,
    request: Request,
    response: Response,
    authenticated: AuthenticatedSession = Depends(get_authenticated_session),
    session: AsyncSession = Depends(get_db_session),
    csrf_header: str | None = Header(default=None, alias="X-CSRF-Token"),
    origin: str | None = Header(default=None, alias="Origin"),
) -> ApiResponse[dict[str, bool]]:
    service = _csrf_service(request, session, authenticated, csrf_header, origin)
    await service.change_password(authenticated, payload.current_password, payload.new_password)
    _delete_session_cookie(response, request.app.state.settings)
    return ok({"changed": True}, get_request_id(request))


@router.put("/session/tenant", response_model=ApiResponse[SessionData])
async def switch_tenant(
    payload: TenantSwitchRequest,
    request: Request,
    authenticated: AuthenticatedSession = Depends(get_authenticated_session),
    session: AsyncSession = Depends(get_db_session),
    csrf_header: str | None = Header(default=None, alias="X-CSRF-Token"),
    origin: str | None = Header(default=None, alias="Origin"),
) -> ApiResponse[SessionData]:
    service = _csrf_service(request, session, authenticated, csrf_header, origin)
    data = await service.switch_tenant(
        authenticated,
        payload.tenant_id,
        get_request_id(request),
    )
    return ok(data, get_request_id(request))


async def _check_login_rate_limit(request: Request, username: str) -> None:
    redis: RedisManager = request.app.state.redis
    source = request.client.host if request.client else "unknown"
    scope = f"login:{source}:{normalize_username(username)}"
    if not await redis.allow(scope, limit=5, window_seconds=300):
        raise AppError("RATE_LIMITED", "Too many login attempts", status.HTTP_429_TOO_MANY_REQUESTS)


def _csrf_service(
    request: Request,
    session: AsyncSession,
    authenticated: AuthenticatedSession,
    csrf_header: str | None,
    origin: str | None,
) -> SessionService:
    settings: AppConfig = request.app.state.settings
    verify_origin(settings, origin)
    service = SessionService(session, settings, request.app.state.database)
    service.verify_csrf(authenticated, csrf_header)
    return service


def _avatar_service(request: Request, session: AsyncSession) -> TenantUserAvatarService:
    return TenantUserAvatarService(
        session,
        request.app.state.database,
        request.app.state.object_storage,
        request.app.state.settings.media.max_user_avatar_bytes,
    )


def _upload_grant_view(grant: ObjectUploadGrant) -> UserAvatarUploadGrantView:
    return UserAvatarUploadGrantView.model_validate(grant, from_attributes=True)


def _set_session_cookie(response: Response, settings: AppConfig, token: str) -> None:
    response.set_cookie(
        settings.security.session_cookie_name,
        token,
        max_age=settings.security.session_absolute_seconds,
        httponly=True,
        secure=settings.security.secure_cookies,
        samesite="lax",
        path="/",
    )


def _delete_session_cookie(response: Response, settings: AppConfig) -> None:
    response.delete_cookie(settings.security.session_cookie_name, path="/")
