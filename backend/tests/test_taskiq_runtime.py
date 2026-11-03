from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from taskiq import ScheduledTask

from app.core.config import load_app_config
from app.modules import taskiq_entrypoints
from app.modules.taskiq_runtime import TaskiqRuntime

ROOT = Path(__file__).resolve().parents[1]


class RecordingScheduleSource:
    def __init__(self) -> None:
        self.deleted: list[str] = []
        self.added: list[ScheduledTask] = []

    async def delete_schedule(self, schedule_id: str) -> None:
        self.deleted.append(schedule_id)

    async def add_schedule(self, schedule: ScheduledTask) -> None:
        self.added.append(schedule)


class RecordingTask:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def kiq(self, tenant_id: str, resource_id: str) -> None:
        self.calls.append((tenant_id, resource_id))


def test_taskiq_runtime_registers_every_background_domain() -> None:
    runtime = TaskiqRuntime(load_app_config(ROOT / "config" / "dev.toml"))

    assert set(runtime.queue.broker.get_all_tasks()) == {
        "parrot.runtime.execute",
        "parrot.memory.index",
        "parrot.knowledge.ingest",
        "parrot.knowledge.staging-cleanup",
        "parrot.knowledge.vector-index",
        "parrot.capability.index",
        "parrot.skills.build",
        "parrot.schedules.execute",
    }


def test_native_taskiq_factories_use_only_explicit_toml_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broker = object()
    scheduler = object()
    runtime = SimpleNamespace(queue=SimpleNamespace(broker=broker, scheduler=scheduler))
    settings = SimpleNamespace(logging=object())
    loaded_paths: list[Path] = []
    configured: list[object] = []

    def load_config(path: Path) -> object:
        loaded_paths.append(path)
        return settings

    def build_runtime(_: Any) -> SimpleNamespace:
        return runtime

    monkeypatch.setattr(taskiq_entrypoints, "load_app_config", load_config)
    monkeypatch.setattr(taskiq_entrypoints, "configure_logging", configured.append)
    monkeypatch.setattr(taskiq_entrypoints, "TaskiqRuntime", build_runtime)

    assert taskiq_entrypoints.local_broker() is broker
    assert taskiq_entrypoints.container_scheduler() is scheduler
    assert loaded_paths == [
        taskiq_entrypoints.DEV_CONFIG_PATH,
        taskiq_entrypoints.CONTAINER_CONFIG_PATH,
    ]
    assert configured == [settings.logging, settings.logging]


@pytest.mark.asyncio
async def test_schedule_task_uses_absolute_time_and_tenant_scoped_identifier() -> None:
    runtime = TaskiqRuntime(load_app_config(ROOT / "config" / "dev.toml"))
    source = RecordingScheduleSource()
    runtime.queue.schedule_source = source  # type: ignore[assignment]
    trigger_at = datetime(2026, 7, 16, 8, 0, tzinfo=UTC)

    await runtime.queue.schedule_task("tenant_test", "schedule_test", trigger_at)

    assert source.deleted == ["schedule:schedule_test"]
    assert len(source.added) == 1
    task = source.added[0]
    assert task.schedule_id == "schedule:schedule_test"
    assert task.args == [
        "tenant_test",
        "schedule_test",
        "2026-07-16T08:00:00+00:00",
    ]


@pytest.mark.asyncio
async def test_scheduler_registers_the_staging_cleanup_cron_once() -> None:
    runtime = TaskiqRuntime(load_app_config(ROOT / "config" / "dev.toml"))
    source = RecordingScheduleSource()
    runtime.queue.schedule_source = source  # type: ignore[assignment]

    await runtime.queue.register_recurring_schedules()

    assert source.deleted == ["recurring:knowledge-staging-cleanup"]
    assert len(source.added) == 1
    task = source.added[0]
    assert task.schedule_id == "recurring:knowledge-staging-cleanup"
    assert task.cron == "0 * * * *"
    assert task.args == []


@pytest.mark.asyncio
async def test_runtime_delivery_is_published_without_the_scheduler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = TaskiqRuntime(load_app_config(ROOT / "config" / "dev.toml"))
    task = RecordingTask()
    source = RecordingScheduleSource()
    monkeypatch.setattr(runtime.queue, "_runtime", task)
    runtime.queue.schedule_source = source  # type: ignore[assignment]

    await runtime.queue.dispatch_runtime("tenant_test", "interaction_test")

    assert task.calls == [("tenant_test", "interaction_test")]
    assert source.deleted == []
    assert source.added == []
