from __future__ import annotations

import httpx
from starlette import status

from app.core.errors import AppError


def validate_model_endpoint(
    value: str,
    *,
    allowed_hosts: tuple[str, ...],
    trusted_hosts: tuple[str, ...] = (),
    trusted_host_suffixes: tuple[str, ...] = (),
    production: bool,
    resource_label: str,
) -> str:
    try:
        endpoint = httpx.URL(value.strip())
    except ValueError as error:
        raise AppError(
            "MODEL_CONFIG_ENDPOINT_INVALID",
            f"{resource_label} endpoint is invalid",
            status.HTTP_422_UNPROCESSABLE_CONTENT,
        ) from error
    if (
        endpoint.scheme not in {"http", "https"}
        or not endpoint.host
        or endpoint.query
        or endpoint.fragment
        or endpoint.username
        or endpoint.password
    ):
        raise AppError(
            "MODEL_CONFIG_ENDPOINT_INVALID",
            f"{resource_label} endpoint is invalid",
            status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    if production and endpoint.scheme != "https":
        raise AppError(
            "MODEL_CONFIG_ENDPOINT_HTTPS_REQUIRED",
            f"{resource_label} endpoint must use HTTPS in production",
            status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    allowed = {host.casefold() for host in allowed_hosts}
    provider_trusted = {host.casefold() for host in trusted_hosts}
    trusted_suffixes = tuple(suffix.casefold() for suffix in trusted_host_suffixes)
    trusted_by_suffix = any(
        endpoint.host.casefold().endswith(suffix) for suffix in trusted_suffixes
    )
    if production and not allowed and not provider_trusted:
        if not trusted_by_suffix:
            raise AppError(
                "MODEL_CONFIG_ENDPOINT_ALLOWLIST_REQUIRED",
                f"{resource_label} endpoint allowlist is not configured",
                status.HTTP_422_UNPROCESSABLE_CONTENT,
            )
    enforce_hosts = production or bool(allowed)
    if (
        enforce_hosts
        and endpoint.host.casefold() not in allowed
        and endpoint.host.casefold() not in provider_trusted
        and not trusted_by_suffix
    ):
        raise AppError(
            "MODEL_CONFIG_ENDPOINT_NOT_ALLOWED",
            f"{resource_label} endpoint is not allowlisted",
            status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    return str(endpoint).rstrip("/")
