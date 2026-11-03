from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import CroniterBadCronError, croniter
from starlette import status

from app.core.errors import AppError


def initial_trigger(
    schedule_type: str,
    cron_expr: str | None,
    run_at: datetime | None,
    timezone_name: str,
    now: datetime,
) -> datetime:
    timezone = _timezone(timezone_name)
    if schedule_type == "once":
        if run_at is None:
            raise _invalid("run_at is required for once schedules")
        aware = run_at if run_at.tzinfo else run_at.replace(tzinfo=timezone)
        value = aware.astimezone(UTC)
        if value <= now:
            raise _invalid("run_at must be in the future")
        return value
    if not cron_expr:
        raise _invalid("cron_expr is required for recurring schedules")
    return next_cron_trigger(cron_expr, timezone_name, now)


def next_cron_trigger(cron_expr: str, timezone_name: str, after: datetime) -> datetime:
    timezone = _timezone(timezone_name)
    if len(cron_expr.split()) != 5:
        raise _invalid("cron_expr must contain exactly five fields")
    try:
        local_after = after.astimezone(timezone)
        value = croniter(cron_expr, local_after).get_next(datetime)
    except (CroniterBadCronError, ValueError) as error:
        raise _invalid("cron_expr is invalid") from error
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone)
    return value.astimezone(UTC)


def _timezone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as error:
        raise _invalid("timezone is invalid") from error


def _invalid(message: str) -> AppError:
    return AppError("SCHEDULE_INVALID", message, status.HTTP_422_UNPROCESSABLE_CONTENT)
