import httpx

from app.modules.model_configs.connection_test import connection_test_failed
from app.modules.model_providers.embedding import ProviderEmbeddingError


def test_every_upstream_diagnostic_field_is_redacted_before_bounding() -> None:
    request = httpx.Request("POST", "https://private-provider.example.test/v1")
    response = httpx.Response(
        401,
        request=request,
        json={
            "error": {
                "message": "x" * 470 + ' api_key="hidden credential with spaces"',
                "code": "Bearer hidden-code",
                "type": "https://private-provider.example.test/internal",
                "request_id": "password=hidden-request-id",
            }
        },
    )
    failed = connection_test_failed(
        httpx.HTTPStatusError(
            "private-exception-content",
            request=request,
            response=response,
        )
    )
    rendered = repr(failed.details)
    for secret in ("hidden", "private-provider", "private-exception-content"):
        assert secret not in rendered
    assert all(len(item["reason"]) <= 500 for item in failed.details)
    assert failed.details[0] == {"field": "upstream_http_status", "reason": "401 Unauthorized"}


def test_custom_diagnostic_fields_are_allowlisted() -> None:
    failed = connection_test_failed(
        ProviderEmbeddingError(
            "invalid response",
            diagnostic_details=[
                {"field": "raw_payload", "reason": "private-provider-body"},
                {"field": "expected_dimension", "reason": "1024"},
                {"field": "actual_dimension", "reason": "512"},
            ],
        )
    )
    assert failed.details == [
        {"field": "expected_dimension", "reason": "1024"},
        {"field": "actual_dimension", "reason": "512"},
    ]
