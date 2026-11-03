from __future__ import annotations

import json
import logging
import sys
from copy import copy
from datetime import UTC, datetime
from types import TracebackType
from typing import Any

from app.core.config import LoggingSection
from app.core.exception_summary import safe_exception_summary
from app.core.redaction import redact_sensitive_text

_SAFE_CONTEXT_FIELDS = (
    "request_id",
    "tenant_id",
    "subject_id",
    "subject_type",
    "route",
    "method",
    "path",
    "status_code",
    "duration_ms",
    "interaction_id",
    "execution_id",
    "job_id",
    "source_id",
    "document_version_id",
    "memory_id",
    "skill_version_id",
)
_OPERATIONAL_LOGGERS = (
    "app",
    "uvicorn",
    "uvicorn.error",
    "uvicorn.access",
    "taskiq",
    "taskiq.worker",
    "taskiq.scheduler",
)
_NOISY_LOGGERS = ("asyncio", "httpcore", "httpx", "pymilvus", "redis", "sqlalchemy.engine")
_LOG_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


class SafeLogFormatter(logging.Formatter):
    def formatException(
        self, ei: tuple[type[BaseException] | None, BaseException | None, TracebackType | None]
    ) -> str:
        return safe_exception_summary(ei[1]) if ei[1] is not None else ""


class JsonLogFormatter(SafeLogFormatter):
    """Emit only safe, operator-useful context fields as structured JSON."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": redact_sensitive_text(record.name),
            "message": redact_sensitive_text(record.getMessage()),
        }
        payload.update(_safe_context(record))
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


class TextLogFormatter(SafeLogFormatter):
    """Append the same allowlisted context to development-friendly text logs."""

    def format(self, record: logging.LogRecord) -> str:
        record = copy(record)
        record.exc_text = None
        record.stack_info = None
        message = super().format(record)
        context = " ".join(f"{field}={value}" for field, value in _safe_context(record).items())
        return redact_sensitive_text(f"{message} {context}" if context else message)


def _safe_context(record: logging.LogRecord) -> dict[str, str | int | float | bool]:
    context: dict[str, str | int | float | bool] = {}
    for field in _SAFE_CONTEXT_FIELDS:
        value = getattr(record, field, None)
        if isinstance(value, str):
            context[field] = redact_sensitive_text(value)
        elif isinstance(value, int | float | bool):
            context[field] = value
    return context


def configure_logging(settings: LoggingSection) -> None:
    """Configure Web and worker logging from the explicitly selected TOML file."""
    level = _validated_level(settings.level)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(_formatter(settings.json_output))
    handler._parrot_configured = True  # type: ignore[attr-defined]

    root = logging.getLogger()
    for existing_handler in tuple(root.handlers):
        if getattr(existing_handler, "_parrot_configured", False):
            root.removeHandler(existing_handler)
    root.addHandler(handler)
    root.setLevel(level)

    for name in _OPERATIONAL_LOGGERS:
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.setLevel(level)
        logger.propagate = True
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)


def _formatter(json_output: bool) -> logging.Formatter:
    if json_output:
        return JsonLogFormatter()
    return TextLogFormatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )


def _validated_level(value: str) -> int:
    try:
        return _LOG_LEVELS[value.upper()]
    except KeyError as error:
        raise ValueError(f"Unsupported logging level: {value}") from error
