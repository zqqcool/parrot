import logging

from app.core.config import LoggingSection
from app.core.observability import JsonLogFormatter, TextLogFormatter, configure_logging


def test_debug_logging_configures_web_and_task_worker_loggers() -> None:
    configure_logging(LoggingSection(level="DEBUG", json=False))

    assert logging.getLogger().level == logging.DEBUG
    assert logging.getLogger("uvicorn.access").level == logging.DEBUG
    assert logging.getLogger("taskiq.worker").level == logging.DEBUG
    assert any(
        isinstance(handler.formatter, TextLogFormatter)
        for handler in logging.getLogger().handlers
        if getattr(handler, "_parrot_configured", False)
    )
    assert logging.getLogger("sqlalchemy.engine").level == logging.WARNING


def test_json_logging_uses_allowlisted_context_only() -> None:
    formatter = JsonLogFormatter()
    record = logging.LogRecord(
        "app.worker",
        logging.INFO,
        __file__,
        1,
        "Task completed",
        (),
        None,
    )
    record.tenant_id = "tenant_123"
    record.private_prompt = "must not be rendered"

    rendered = formatter.format(record)

    assert '"tenant_id": "tenant_123"' in rendered
    assert "private_prompt" not in rendered
