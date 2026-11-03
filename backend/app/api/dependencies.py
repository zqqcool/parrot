from __future__ import annotations

from collections.abc import AsyncGenerator, Callable, Coroutine
from typing import Any

from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.config import AppConfig
from app.core.errors import AppError
from app.core.request_id import get_request_id
from app.infrastructure.db.session import DatabaseManager
from app.modules.iam.service import AuthenticatedSession, SessionService


async def get_db_session(request: Request) -> AsyncGenerator[AsyncSession]:
    database: DatabaseManager = request.app.state.database
    async with database.session() as session:
        yield session


async def get_authenticated_session(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> AuthenticatedSession:
    settings: AppConfig = request.app.state.settings
    raw_token = request.cookies.get(settings.security.session_cookie_name)
    return await SessionService(session, settings, request.app.state.database).authenticate(
        raw_token, get_request_id(request)
    )


PermissionDependency = Callable[..., Coroutine[Any, Any, AuthenticatedSession]]


def require_permission(permission: str, *, csrf: bool = False) -> PermissionDependency:
    async def dependency_with_session(
        request: Request,
        session: AsyncSession = Depends(get_db_session),
        authenticated: AuthenticatedSession = Depends(get_authenticated_session),
        csrf_header: str | None = Header(default=None, alias="X-CSRF-Token"),
        origin: str | None = Header(default=None, alias="Origin"),
    ) -> AuthenticatedSession:
        if permission not in authenticated.principal.permissions:
            raise AppError("FORBIDDEN", "Permission denied", status.HTTP_403_FORBIDDEN)
        if csrf:
            settings: AppConfig = request.app.state.settings
            verify_origin(settings, origin)
            SessionService(session, settings, request.app.state.database).verify_csrf(
                authenticated, csrf_header
            )
        return authenticated

    return dependency_with_session


def verify_origin(settings: AppConfig, origin: str | None) -> None:
    allowed = settings.security.allowed_origins
    if allowed and origin not in allowed:
        raise AppError("ORIGIN_INVALID", "Origin validation failed", status.HTTP_403_FORBIDDEN)
