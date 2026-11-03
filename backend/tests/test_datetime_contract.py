from __future__ import annotations

from datetime import UTC

from sqlalchemy import DateTime

from app.core.clock import SystemClock
from app.infrastructure.db.base import Base
from app.modules import models


def test_system_clock_returns_aware_utc_time() -> None:
    value = SystemClock().now()

    assert value.tzinfo is UTC
    assert value.utcoffset() is not None


def test_all_persisted_datetime_columns_are_timezone_aware() -> None:
    assert models is not None
    invalid = sorted(
        f"{table.name}.{column.name}"
        for table in Base.metadata.sorted_tables
        for column in table.columns
        if isinstance(column.type, DateTime) and not column.type.timezone
    )

    assert invalid == []
