import json
import logging
import sys
from pathlib import Path
from traceback import format_exception

import httpx
import pytest

from app.core.config import load_app_config
from app.core.observability import JsonLogFormatter, TextLogFormatter
from app.core.redaction import redact_sensitive_text
from app.main import create_app
from app.modules.agent_runtime.model_observation import tool_result_message


@pytest.mark.parametrize(
    "text,secret",
    [
        ("Bearer hidden-token", "hidden-token"),
        ("bearer\thidden-token", "hidden-token"),
        ('{"api_key": "private value with spaces"}', "private value with spaces"),
        ("password='private value'", "private value"),
        ("Cookie: session=hidden-cookie; csrf=hidden-cookie", "hidden-cookie"),
        ("https://user:hidden-password@host.test/path", "hidden-password"),
        ("https://host.test/path?access_token=hidden-query&limit=1", "hidden-query"),
        (
            "-----BEGIN PRIVATE KEY-----\nprivate material\n-----END PRIVATE KEY-----",
            "private material",
        ),
    ],
)
def test_sensitive_text_is_redacted_before_output(text: str, secret: str) -> None:
    rendered = redact_sensitive_text(text)
    assert secret not in rendered
    assert "[REDACTED]" in rendered


def test_model_observation_redacts_nested_credentials_and_preserves_evidence_urls() -> None:
    result = tool_result_message(
        {
            "status": "ok",
            "content": "Authorization: Bearer hidden-bearer",
            "details": [{"API-Key": "hidden-key", "Cookie": "hidden-cookie"}],
            "source": "https://docs.example.test/page",
        }
    )
    assert "hidden-" not in result
    assert json.loads(result)["source"] == "https://docs.example.test/page"


@pytest.mark.parametrize("json_output", [False, True])
def test_logs_keep_call_sites_and_request_id_without_exception_content(json_output: bool) -> None:
    try:
        try:
            raise ValueError("private-prompt-content and sql-parameter-value")
        except ValueError as cause:
            raise RuntimeError("provider-credential-content") from cause
    except RuntimeError:
        record = logging.LogRecord(
            "app.worker",
            logging.ERROR,
            __file__,
            1,
            "Provider failed: Bearer hidden-token",
            (),
            sys.exc_info(),
        )
    record.request_id = "req_safe"
    record.private_prompt = "private-prompt-content"
    record.exc_text = "cached-private-exception"
    record.stack_info = "private-stack-source"
    formatter = JsonLogFormatter() if json_output else TextLogFormatter()
    rendered = formatter.format(record)

    for secret in (
        "hidden-token",
        "private-prompt-content",
        "sql-parameter-value",
        "provider-credential-content",
        "cached-private-exception",
        "private-stack-source",
    ):
        assert secret not in rendered
    assert "req_safe" in rendered
    assert "RuntimeError" in rendered
    assert "ValueError" in rendered
    assert "test_redaction.py:" in rendered
    assert str(Path(__file__).parent) not in rendered
    if json_output:
        assert json.loads(rendered)["request_id"] == "req_safe"


def test_config_failure_does_not_print_pydantic_inputs(tmp_path: Path) -> None:
    path = tmp_path / "dev.toml"
    path.write_text('[app]\nenvironment = "private-config-value"\n')
    with pytest.raises(RuntimeError) as error:
        load_app_config(path)
    assert "private-config-value" not in "".join(format_exception(error.value))


@pytest.mark.asyncio
async def test_public_configuration_uses_generic_error_responses() -> None:
    settings = load_app_config(Path(__file__).resolve().parents[1] / "config/dev.toml")
    app = create_app(settings)

    async def fail() -> None:
        raise RuntimeError("hidden-exception-prompt")

    app.add_api_route("/test-redaction", fail, methods=["GET"])
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/test-redaction", headers={"X-Request-Id": "req_redaction"})
    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_ERROR"
    assert response.json()["request_id"] == "req_redaction"
    assert "hidden-exception-prompt" not in response.text
