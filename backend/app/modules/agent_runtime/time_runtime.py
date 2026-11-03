from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_COMPACT_DURATION = re.compile(r"(?P<value>\d+(?:\.\d+)?)(?P<unit>ms|s|m|h|d|w)", re.I)
_ISO_DURATION = re.compile(
    r"^P(?:(?P<weeks>\d+(?:\.\d+)?)W)?(?:(?P<days>\d+(?:\.\d+)?)D)?"
    r"(?:T(?:(?P<hours>\d+(?:\.\d+)?)H)?(?:(?P<minutes>\d+(?:\.\d+)?)M)?"
    r"(?:(?P<seconds>\d+(?:\.\d+)?)S)?)?$",
    re.I,
)
_DATE_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y/%m/%d")


class TimeRuntimePort(Protocol):
    async def handle(self, arguments: dict[str, object]) -> dict[str, object]: ...


class BuiltinTimeRuntime:
    def __init__(self, default_timezone: str) -> None:
        self._default_timezone = default_timezone

    async def handle(self, arguments: dict[str, object]) -> dict[str, object]:
        try:
            return _handle(arguments, self._default_timezone)
        except ValueError as error:
            return {"status": "rejected", "code": "TIME_INPUT_INVALID", "message": str(error)}


def _handle(arguments: dict[str, object], default_timezone: str) -> dict[str, object]:
    action = _required_text(arguments.get("action"), "action")
    timezone = _timezone(arguments.get("timezone"), default_timezone)
    if action == "now":
        return _success(action, {"now": _view(datetime.now(timezone))})
    if action == "parse":
        value = _parse(arguments.get("value"), timezone)
        return _success(action, {"parsed": _view(value)})
    if action == "diff":
        start = _parse(arguments.get("start"), timezone)
        end = (
            _parse(arguments.get("end"), timezone)
            if arguments.get("end") is not None
            else datetime.now(timezone)
        )
        seconds = (end.astimezone(UTC) - start.astimezone(UTC)).total_seconds()
        return _success(action, {"start": _view(start), "end": _view(end), "seconds": seconds})
    if action in {"add", "subtract"}:
        value = _parse(arguments.get("value", "now"), timezone)
        duration = _duration(arguments.get("duration"))
        result = value + (duration if action == "add" else -duration)
        return _success(action, {"base": _view(value), "result": _view(result)})
    if action == "convert_timezone":
        value = _parse(arguments.get("value"), timezone)
        target = _timezone(arguments.get("target_timezone"), default_timezone)
        return _success(action, {"result": _view(value.astimezone(target))})
    if action == "format":
        value = _parse(arguments.get("value"), timezone)
        return _success(action, {"formatted": _format(value, arguments)})
    raise ValueError("Unsupported time action")


def _timezone(value: object, default_timezone: str) -> ZoneInfo:
    name = value.strip() if isinstance(value, str) and value.strip() else default_timezone
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as error:
        raise ValueError("Timezone is unavailable") from error


def _parse(value: object, timezone: ZoneInfo) -> datetime:
    if isinstance(value, bool) or value is None:
        raise ValueError("A time value is required")
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=UTC).astimezone(timezone)
    if not isinstance(value, str) or not value.strip() or len(value) > 200:
        raise ValueError("A valid time value is required")
    normalized = value.strip().casefold()
    now = datetime.now(timezone)
    if normalized == "now":
        return now
    if normalized in {"today", "tomorrow", "yesterday"}:
        days = {"today": 0, "tomorrow": 1, "yesterday": -1}[normalized]
        return (now + timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        parsed = _parse_known_format(value.strip())
    return parsed.replace(tzinfo=timezone) if parsed.tzinfo is None else parsed.astimezone(timezone)


def _parse_known_format(value: str) -> datetime:
    for pattern in _DATE_FORMATS:
        try:
            return datetime.strptime(value, pattern)
        except ValueError:
            continue
    raise ValueError("Time value is not parseable")


def _duration(value: object) -> timedelta:
    if not isinstance(value, str) or not value.strip() or len(value) > 120:
        raise ValueError("duration is required")
    normalized = value.strip().upper()
    match = _ISO_DURATION.fullmatch(normalized)
    if match:
        values = {key: float(item or 0) for key, item in match.groupdict().items()}
        return timedelta(**values)
    compact = "".join(normalized.split()).lower()
    matches = list(_COMPACT_DURATION.finditer(compact))
    if not matches or "".join(item.group(0) for item in matches) != compact:
        raise ValueError("duration is invalid")
    seconds = sum(_duration_seconds(float(item["value"]), item["unit"].lower()) for item in matches)
    return timedelta(seconds=seconds)


def _duration_seconds(value: float, unit: str) -> float:
    units = {"ms": 0.001, "s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
    return value * units[unit]


def _format(value: datetime, arguments: dict[str, object]) -> str | int:
    output_format = _required_text(arguments.get("output_format", "iso"), "output_format")
    if output_format == "iso":
        return value.isoformat()
    if output_format == "date":
        return value.date().isoformat()
    if output_format == "datetime":
        return value.strftime("%Y-%m-%d %H:%M:%S %Z")
    if output_format == "timestamp":
        return int(value.timestamp())
    if output_format == "strftime":
        pattern = _required_text(arguments.get("strftime_format"), "strftime_format")
        if len(pattern) > 100:
            raise ValueError("strftime format is too long")
        return value.strftime(pattern)
    raise ValueError("output_format is unsupported")


def _view(value: datetime) -> dict[str, object]:
    return {
        "iso": value.isoformat(),
        "timestamp": int(value.timestamp()),
        "timezone": str(value.tzinfo),
    }


def _required_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    return value.strip().casefold()


def _success(action: str, result: dict[str, object]) -> dict[str, object]:
    return {"status": "ok", "action": action, "result": result}
