from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.clock import utc_now
from app.core.config import AppConfig
from app.core.errors import AppError
from app.core.ids import new_id
from app.core.security import (
    constant_time_equal,
    csrf_token,
    hash_password,
    new_secret,
    secret_digest,
    verify_password,
)
from app.infrastructure.db.session import DatabaseManager
from app.modules.iam.models import Session, User
from app.modules.iam.repository import IamRepository
from app.modules.iam.schemas import PrincipalContext, SessionData, TenantAccess


@dataclass(frozen=True)
class CreatedSession:
    raw_token: str
    session: Session
    data: SessionData


@dataclass(frozen=True)
class AuthenticatedSession:
    raw_token: str
    session: Session
    principal: PrincipalContext


class SessionService:
    def __init__(
        self,
        db: AsyncSession,
        settings: AppConfig,
        database: DatabaseManager,
    ) -> None:
        self.repository = IamRepository(db)
        self.settings = settings
        self.database = database

    async def login(
        self,
        username: str,
        password: str,
        request_id: str,
        user_agent: str | None,
    ) -> CreatedSession:
        user = await self.repository.get_user_by_username(normalize_username(username))
        credential = await self.repository.get_credential(user.id) if user else None
        if not user or not credential or not verify_password(password, credential.password_hash):
            raise AppError(
                "AUTH_INVALID_CREDENTIALS",
                "Invalid username or password",
                status.HTTP_401_UNAUTHORIZED,
            )
        if user.status != "active":
            raise AppError("AUTH_USER_DISABLED", "User is disabled", status.HTTP_403_FORBIDDEN)

        await self.database.set_principal(self.repository.session, user.id, None)
        tenants = await self.repository.list_tenant_access(user.id)
        current_tenant_id = tenants[0][1].id if tenants else None
        await self.database.set_principal(self.repository.session, user.id, current_tenant_id)
        now = utc_now()
        raw_token = new_secret("ses")
        session = Session(
            id=new_id("session"),
            user_id=user.id,
            current_tenant_id=current_tenant_id,
            token_hash=self._token_hash(raw_token),
            expires_at=now + timedelta(seconds=self.settings.security.session_absolute_seconds),
            idle_expires_at=now + timedelta(seconds=self.settings.security.session_idle_seconds),
            last_seen_at=now,
            user_agent=(user_agent or "")[:512] or None,
        )
        await self.repository.create_session(session)
        user.last_login_at = now
        principal = await self._principal(user, current_tenant_id, request_id)
        return CreatedSession(
            raw_token=raw_token,
            session=session,
            data=self._session_data(raw_token, session, principal),
        )

    async def authenticate(self, raw_token: str | None, request_id: str) -> AuthenticatedSession:
        if not raw_token:
            raise AppError("UNAUTHORIZED", "Authentication required", status.HTTP_401_UNAUTHORIZED)
        session = await self.repository.get_session_by_hash(self._token_hash(raw_token))
        now = utc_now()
        if (
            not session
            or session.revoked_at
            or session.expires_at <= now
            or session.idle_expires_at <= now
        ):
            raise AppError(
                "UNAUTHORIZED", "Session is invalid or expired", status.HTTP_401_UNAUTHORIZED
            )
        user = await self.repository.get_user(session.user_id)
        if not user or user.status != "active":
            if session:
                await self.repository.revoke_session(session.id, now)
            raise AppError("UNAUTHORIZED", "Session is invalid", status.HTTP_401_UNAUTHORIZED)

        await self.database.set_principal(
            self.repository.session, user.id, session.current_tenant_id
        )
        idle_expires = min(
            session.expires_at,
            now + timedelta(seconds=self.settings.security.session_idle_seconds),
        )
        await self.repository.touch_session(session.id, now, idle_expires)
        principal = await self._principal(user, session.current_tenant_id, request_id)
        return AuthenticatedSession(raw_token=raw_token, session=session, principal=principal)

    async def session_data(self, authenticated: AuthenticatedSession) -> SessionData:
        return self._session_data(
            authenticated.raw_token,
            authenticated.session,
            authenticated.principal,
        )

    async def switch_tenant(
        self,
        authenticated: AuthenticatedSession,
        tenant_id: str,
        request_id: str,
    ) -> SessionData:
        tenant_ids = {tenant.id for tenant in authenticated.principal.tenants}
        if (
            tenant_id not in tenant_ids
            and "platform.tenants.manage" not in authenticated.principal.permissions
        ):
            raise AppError("RESOURCE_NOT_FOUND", "Tenant not found", status.HTTP_404_NOT_FOUND)
        await self.repository.set_session_tenant(authenticated.session.id, tenant_id)
        user = await self.repository.get_user(authenticated.session.user_id)
        if user is None:
            raise AppError("UNAUTHORIZED", "User not found", status.HTTP_401_UNAUTHORIZED)
        authenticated.session.current_tenant_id = tenant_id
        await self.database.set_principal(self.repository.session, user.id, tenant_id)
        principal = await self._principal(user, tenant_id, request_id)
        return self._session_data(authenticated.raw_token, authenticated.session, principal)

    async def change_password(
        self,
        authenticated: AuthenticatedSession,
        current_password: str,
        new_password: str,
    ) -> None:
        self._validate_new_password(new_password)
        credential = await self.repository.get_credential(authenticated.session.user_id)
        if not credential or not verify_password(current_password, credential.password_hash):
            raise AppError(
                "AUTH_INVALID_PASSWORD", "Current password is invalid", status.HTTP_400_BAD_REQUEST
            )
        await self.repository.update_password(
            authenticated.session.user_id, hash_password(new_password)
        )
        await self.repository.revoke_user_sessions(authenticated.session.user_id)

    async def logout(self, authenticated: AuthenticatedSession) -> None:
        await self.repository.revoke_session(authenticated.session.id)

    def verify_csrf(self, authenticated: AuthenticatedSession, supplied: str | None) -> None:
        expected = csrf_token(authenticated.raw_token, self.settings.security.session_pepper)
        if not supplied or not constant_time_equal(supplied, expected):
            raise AppError("CSRF_INVALID", "CSRF validation failed", status.HTTP_403_FORBIDDEN)

    def _validate_new_password(self, password: str) -> None:
        if len(password) < self.settings.security.password_min_length:
            raise AppError(
                "AUTH_PASSWORD_WEAK",
                "Password must contain at least "
                f"{self.settings.security.password_min_length} characters",
            )

    async def _principal(
        self,
        user: User,
        tenant_id: str | None,
        request_id: str,
    ) -> PrincipalContext:
        access = await self.repository.list_tenant_access(user.id)
        permissions = await self.repository.effective_permissions(user.id, tenant_id)
        return PrincipalContext(
            tenant_id=tenant_id,
            subject_id=user.id,
            username=user.username,
            display_name=user.display_name,
            avatar_present=bool(user.avatar_key and user.avatar_content_type),
            permissions=tuple(sorted(permissions)),
            tenants=tuple(
                TenantAccess(id=tenant.id, slug=tenant.slug, name=tenant.name)
                for _membership, tenant in access
            ),
            must_change_password=user.must_change_password,
            request_id=request_id,
        )

    def _session_data(
        self,
        raw_token: str,
        session: Session,
        principal: PrincipalContext,
    ) -> SessionData:
        return SessionData(
            principal=principal,
            csrf_token=csrf_token(raw_token, self.settings.security.session_pepper),
            expires_at=session.expires_at,
            password_min_length=self.settings.security.password_min_length,
            default_schedule_timezone=self.settings.schedules.default_timezone,
        )

    def _token_hash(self, token: str) -> str:
        return secret_digest(token, self.settings.security.session_pepper, "session")


def normalize_username(value: str) -> str:
    return value.strip().casefold()
