from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.modules.runs.legacy_cleanup import LegacyRunCleanupService


class CleanupDatabase:
    def __init__(self) -> None:
        self.platform = SimpleNamespace(
            scalars=AsyncMock(return_value=["tenant_one", "tenant_two"])
        )
        self.session_value = SimpleNamespace()
        self.set_tenant = AsyncMock()

    @asynccontextmanager
    async def platform_session(self):
        yield self.platform

    @asynccontextmanager
    async def session(self):
        yield self.session_value


@pytest.mark.asyncio
async def test_legacy_cleanup_dry_run_never_deletes(monkeypatch: pytest.MonkeyPatch) -> None:
    repository = SimpleNamespace(
        count_legacy_chat_runs=AsyncMock(side_effect=[3, 0]),
        delete_legacy_chat_runs=AsyncMock(),
    )
    monkeypatch.setattr(
        "app.modules.runs.legacy_cleanup.RunRepository", lambda _session: repository
    )

    summaries = await LegacyRunCleanupService(CleanupDatabase()).run(confirm=False)

    assert [summary.candidate_count for summary in summaries] == [3, 0]
    assert [summary.deleted_count for summary in summaries] == [0, 0]
    repository.delete_legacy_chat_runs.assert_not_awaited()


@pytest.mark.asyncio
async def test_legacy_cleanup_deletes_per_tenant_only_after_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = SimpleNamespace(
        count_legacy_chat_runs=AsyncMock(side_effect=[2, 1]),
        delete_legacy_chat_runs=AsyncMock(side_effect=[2, 1]),
    )
    monkeypatch.setattr(
        "app.modules.runs.legacy_cleanup.RunRepository", lambda _session: repository
    )

    summaries = await LegacyRunCleanupService(CleanupDatabase()).run(confirm=True)

    assert [summary.candidate_count for summary in summaries] == [2, 1]
    assert [summary.deleted_count for summary in summaries] == [2, 1]
    assert repository.delete_legacy_chat_runs.await_args_list[0].args == ("tenant_one",)
    assert repository.delete_legacy_chat_runs.await_args_list[1].args == ("tenant_two",)
