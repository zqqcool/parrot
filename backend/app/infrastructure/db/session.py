from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import DatabaseSection


class DatabaseManager:
    def __init__(self, config: DatabaseSection) -> None:
        self.enabled = config.enabled
        self.engine = create_async_engine(
            config.url,
            pool_pre_ping=True,
            pool_size=config.pool_size,
            max_overflow=config.max_overflow,
        )
        self.session_factory = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
        self.platform_engine = create_async_engine(
            config.platform_url,
            pool_pre_ping=True,
            pool_size=min(config.pool_size, 2),
            max_overflow=0,
        )
        self.platform_session_factory = async_sessionmaker(
            bind=self.platform_engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession]:
        async with self._managed_session(self.session_factory) as session:
            yield session

    @asynccontextmanager
    async def platform_session(self) -> AsyncGenerator[AsyncSession]:
        async with self._managed_session(self.platform_session_factory) as session:
            yield session

    @asynccontextmanager
    async def _managed_session(
        self, factory: async_sessionmaker[AsyncSession]
    ) -> AsyncGenerator[AsyncSession]:
        async with factory() as session:
            try:
                yield session
                if session.in_transaction():
                    await session.commit()
            except Exception:
                if session.in_transaction():
                    await session.rollback()
                raise

    async def ping(self) -> bool:
        if not self.enabled:
            return False
        async with self.session_factory() as session:
            await session.execute(text("SELECT 1"))
        return True

    async def set_tenant(self, session: AsyncSession, tenant_id: str) -> None:
        await session.execute(
            text("SELECT set_config('app.current_tenant_id', :tenant_id, true)"),
            {"tenant_id": tenant_id},
        )

    async def set_principal(
        self,
        session: AsyncSession,
        user_id: str,
        tenant_id: str | None,
    ) -> None:
        await session.execute(
            text("SELECT set_config('app.current_user_id', :user_id, true)"),
            {"user_id": user_id},
        )
        await session.execute(
            text("SELECT set_config('app.current_tenant_id', :tenant_id, true)"),
            {"tenant_id": tenant_id or ""},
        )

    async def dispose(self) -> None:
        await self.engine.dispose()
        await self.platform_engine.dispose()
