from __future__ import annotations

from collections.abc import Iterable
from typing import cast

import httpx
from starlette import status

from app.core.errors import AppError
from app.core.redaction import redact_sensitive_text

CONNECTION_TEST_TIMEOUT_SECONDS = 30
_REQUEST_ID_HEADERS = ("x-request-id", "x-tt-logid", "request-id")
_CUSTOM_DETAIL_FIELDS = {
    "expected_response_count",
    "actual_response_count",
    "expected_dimension",
    "actual_dimension",
}
_LOCAL_DIAGNOSTICS = {
    "Model provider response is invalid": "供应商响应不符合 OpenAI Chat Completions 协议。",
    "Embedding provider request failed": "供应商响应不是有效的 Embedding 响应。",
    "Reranker provider response is invalid": "供应商响应不是有效的重排序响应。",
    "Configured model credential is missing": "未配置模型凭据。",
    "Configured model credential is unavailable": "模型凭据无法解密或读取。",
}


def connection_test_failed(error: BaseException | None = None) -> AppError:
    return AppError(
        "MODEL_CONFIG_CONNECTION_FAILED",
        "Model connection test failed",
        status.HTTP_502_BAD_GATEWAY,
        details=_connection_details(error),
    )


def _connection_details(error: BaseException | None) -> list[dict[str, str]]:
    if error is None:
        return []
    chain = tuple(_error_chain(error))
    custom_match = next(
        (details for item in chain if (details := _custom_details(item)) is not None),
        None,
    )
    custom: list[dict[str, str]] = custom_match or []
    http_status = next((item for item in chain if isinstance(item, httpx.HTTPStatusError)), None)
    if http_status is not None:
        return [*custom, *_http_status_details(http_status.response)]
    request_error = next((item for item in chain if isinstance(item, httpx.RequestError)), None)
    if request_error is not None:
        return [
            *custom,
            {"field": "failure_type", "reason": "网络连接失败"},
            {"field": "network_error", "reason": type(request_error).__name__},
        ]
    diagnostic = next((_LOCAL_DIAGNOSTICS.get(str(item)) for item in chain), None)
    if diagnostic:
        return [*custom, {"field": "diagnostic", "reason": diagnostic}]
    return custom


def _error_chain(error: BaseException) -> Iterable[BaseException]:
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def _http_status_details(response: httpx.Response) -> list[dict[str, str]]:
    details = [
        {
            "field": "upstream_http_status",
            "reason": str(response.status_code)
            + " "
            + httpx.codes.get_reason_phrase(response.status_code),
        }
    ]
    payload = _json_object(response)
    error_value = payload.get("error")
    provider_error = (
        cast(dict[str, object], error_value) if isinstance(error_value, dict) else payload
    )
    _append_detail(details, "upstream_error_code", provider_error.get("code"))
    _append_detail(details, "upstream_error_type", provider_error.get("type"))
    _append_detail(details, "upstream_message", provider_error.get("message"))
    request_id = provider_error.get("request_id") or payload.get("request_id")
    if request_id is None:
        request_id = next(
            (
                response.headers.get(name)
                for name in _REQUEST_ID_HEADERS
                if response.headers.get(name)
            ),
            None,
        )
    _append_detail(details, "upstream_request_id", request_id)
    return details


def _json_object(response: httpx.Response) -> dict[str, object]:
    try:
        value = cast(object, response.json())
    except ValueError:
        return {}
    return cast(dict[str, object], value) if isinstance(value, dict) else {}


def _append_detail(details: list[dict[str, str]], field: str, value: object) -> None:
    if not isinstance(value, str | int) or isinstance(value, bool):
        return
    normalized = redact_sensitive_text(" ".join(str(value).split()), hide_urls=True)[:500]
    if normalized:
        details.append({"field": field, "reason": normalized})


def _custom_details(error: BaseException) -> list[dict[str, str]] | None:
    values = error.__dict__.get("diagnostic_details")
    if not isinstance(values, list):
        return None
    details: list[dict[str, str]] = []
    for value in cast(list[object], values):
        if not isinstance(value, dict):
            continue
        item = cast(dict[object, object], value)
        field = item.get("field")
        reason = item.get("reason")
        if not isinstance(field, str) or field not in _CUSTOM_DETAIL_FIELDS:
            continue
        _append_detail(details, field, reason)
    return details
