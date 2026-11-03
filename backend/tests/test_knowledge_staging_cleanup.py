from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import Clock
from app.core.config import AppConfig
from app.core.object_storage import ObjectStoragePort
from app.modules.knowledge.models import KnowledgeSource
from app.modules.knowledge.staging_cleanup_worker import (
    KnowledgeStagingCleanupWorker,
    StaleKnowledgeSource,
)


class FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 7, 24, tzinfo=UTC)


class FakeDatabase:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.tenant_ids: list[str] = []

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession]:
        yield self._session

    async def set_tenant(self, _session: AsyncSession, tenant_id: str) -> None:
        self.tenant_ids.append(tenant_id)

    async def dispose(self) -> None:
        return None


@pytest.mark.asyncio
async def test_staging_cleanup_revalidates_the_tenant_source_before_deleting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = KnowledgeSource(
        id="source_staging",
        tenant_id="tenant_test",
        space_id="space_test",
        source_kind="upload",
        title="Release runbook",
        original_filename="release.md",
        content_type="text/markdown",
        declared_size_bytes=1024,
        staging_key="staging/knowledge/tenant_test/source_staging/upload.md",
        status="staging",
        created_by_user_id="user_test",
    )
    add = Mock()
    delete = AsyncMock()
    session = cast(AsyncSession, SimpleNamespace(add=add, delete=delete))
    database = FakeDatabase(session)
    settings = SimpleNamespace(
        database=SimpleNamespace(),
        knowledge=SimpleNamespace(staging_retention_hours=24),
    )
    delete_object = AsyncMock()
    storage = cast(ObjectStoragePort, SimpleNamespace(delete=delete_object))

    def database_manager(_config: object) -> FakeDatabase:
        return database

    monkeypatch.setattr(
        "app.modules.knowledge.staging_cleanup_worker.DatabaseManager",
        database_manager,
    )
    monkeypatch.setattr(
        "app.modules.knowledge.staging_cleanup_worker._stale_source_for_update",
        AsyncMock(return_value=source),
    )
    worker = KnowledgeStagingCleanupWorker(
        cast(AppConfig, settings),
        storage,
        clock=cast(Clock, FixedClock()),
    )
    monkeypatch.setattr(
        worker,
        "_find_candidates",
        AsyncMock(return_value=(StaleKnowledgeSource("tenant_test", source.id),)),
    )

    deleted_count = await worker.process()

    assert deleted_count == 1
    assert database.tenant_ids == ["tenant_test"]
    assert delete_object.await_count == 1
    assert delete.await_count == 1
    assert add.call_args.args[0].actor_type == "system"
