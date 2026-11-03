from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    """Application clock for deterministic lease, expiry, and scheduling decisions."""

    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


SYSTEM_CLOCK = SystemClock()


def utc_now() -> datetime:
    """Return an aware UTC timestamp for persistence and API contracts."""

    return SYSTEM_CLOCK.now()
