"""Native TaskIQ CLI factories with explicit configuration selection."""

from __future__ import annotations

from pathlib import Path

from taskiq import TaskiqScheduler
from taskiq_redis import RedisStreamBroker

from app.core.config import load_app_config
from app.core.observability import configure_logging
from app.modules.taskiq_runtime import TaskiqRuntime

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEV_CONFIG_PATH = _BACKEND_ROOT / "config" / "dev.toml"
CONTAINER_CONFIG_PATH = Path("/etc/parrot/config.toml")


def local_broker() -> RedisStreamBroker:
    """Return the broker for the repository's explicit development TOML file."""
    return _runtime_for(DEV_CONFIG_PATH).queue.broker


def local_scheduler() -> TaskiqScheduler:
    """Return the scheduler for the repository's explicit development TOML file."""
    return _runtime_for(DEV_CONFIG_PATH).queue.scheduler


def container_broker() -> RedisStreamBroker:
    """Return the broker for the container image's explicit TOML file."""
    return _runtime_for(CONTAINER_CONFIG_PATH).queue.broker


def container_scheduler() -> TaskiqScheduler:
    """Return the scheduler for the container image's explicit TOML file."""
    return _runtime_for(CONTAINER_CONFIG_PATH).queue.scheduler


def _runtime_for(config_path: Path) -> TaskiqRuntime:
    settings = load_app_config(config_path)
    configure_logging(settings.logging)
    return TaskiqRuntime(settings)
