from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import utc_now
from app.core.config import AppConfig
from app.core.ids import new_id
from app.core.security import new_secret, secret_digest
from app.infrastructure.db.session import DatabaseManager
from app.modules.anonymous.models import AnonymousSession


@dataclass(frozen=True)
class ResolvedVisitor:
    session: AnonymousSession
    raw_token: str
    is_new: bool


class AnonymousSessionService:
    def __init__(
        self,
        session: AsyncSession,
        settings: AppConfig,
        database: DatabaseManager,
    ) -> None:
        self.session = session
        self.settings = settings
        self.database = database

    async def resolve(self, raw_token: str | None, tenant_id: str) -> ResolvedVisitor:
        await self.database.set_tenant(self.session, tenant_id)
        now = utc_now()
        model = await self._find(raw_token) if raw_token else None
        if model and model.tenant_id == tenant_id and model.expires_at > now:
            await self.session.execute(
                update(AnonymousSession)
                .where(AnonymousSession.id == model.id)
                .values(last_seen_at=now)
            )
            return ResolvedVisitor(session=model, raw_token=raw_token or "", is_new=False)

        token = f"v1.{tenant_id}.{new_secret('visitor')}"
        model = AnonymousSession(
            id=new_id("visitor"),
            tenant_id=tenant_id,
            token_hash=self._hash(token),
            expires_at=now + timedelta(seconds=self.settings.anonymous.session_ttl_seconds),
            last_seen_at=now,
        )
        self.session.add(model)
        await self.session.flush()
        return ResolvedVisitor(session=model, raw_token=token, is_new=True)

    async def authenticate(self, raw_token: str | None) -> AnonymousSession | None:
        if not raw_token:
            return None
        tenant_id = _tenant_from_token(raw_token)
        if tenant_id is None:
            return None
        await self.database.set_tenant(self.session, tenant_id)
        model = await self._find(raw_token)
        if model is None or model.expires_at <= utc_now():
            return None
        return model

    async def _find(self, token: str) -> AnonymousSession | None:
        result = await self.session.execute(
            select(AnonymousSession).where(AnonymousSession.token_hash == self._hash(token))
        )
        return result.scalar_one_or_none()

    def _hash(self, token: str) -> str:
        return secret_digest(token, self.settings.security.session_pepper, "visitor")


def _tenant_from_token(token: str) -> str | None:
    parts = token.split(".", maxsplit=2)
    if len(parts) != 3 or parts[0] != "v1" or not parts[1]:
        return None
    return parts[1]
