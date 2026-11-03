from __future__ import annotations

import json
from dataclasses import dataclass
from typing import cast

from app.modules.model_providers.catalog import CredentialType

_ENVELOPE_VERSION = 1


class RerankerCredentialError(ValueError):
    def __init__(self, field: str) -> None:
        self.field = field
        super().__init__(f"Reranker credential field is invalid: {field}")


@dataclass(frozen=True)
class RerankerProviderCredential:
    credential_type: CredentialType
    api_key: str | None = None
    access_key_id: str | None = None
    secret_access_key: str | None = None


def build_reranker_credential(
    credential_type: CredentialType,
    *,
    api_key: str | None = None,
    access_key_id: str | None = None,
    secret_access_key: str | None = None,
) -> RerankerProviderCredential:
    if credential_type == "api_key":
        return RerankerProviderCredential(
            credential_type=credential_type,
            api_key=_required(api_key, "api_key"),
        )
    return RerankerProviderCredential(
        credential_type=credential_type,
        access_key_id=_required(access_key_id, "access_key_id"),
        secret_access_key=_required(secret_access_key, "secret_access_key"),
    )


def encode_reranker_credential(credential: RerankerProviderCredential) -> str:
    if credential.credential_type == "api_key":
        return _required(credential.api_key, "api_key")
    payload = {
        "version": _ENVELOPE_VERSION,
        "type": credential.credential_type,
        "access_key_id": _required(credential.access_key_id, "access_key_id"),
        "secret_access_key": _required(credential.secret_access_key, "secret_access_key"),
    }
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def decode_reranker_credential(
    value: str, credential_type: CredentialType
) -> RerankerProviderCredential:
    if credential_type == "api_key":
        return build_reranker_credential(credential_type, api_key=value)
    try:
        payload = cast(object, json.loads(value))
    except (TypeError, ValueError) as error:
        raise RerankerCredentialError("credential_envelope") from error
    if not isinstance(payload, dict):
        raise RerankerCredentialError("credential_envelope")
    values = cast(dict[str, object], payload)
    if values.get("version") != _ENVELOPE_VERSION or values.get("type") != credential_type:
        raise RerankerCredentialError("credential_envelope")
    return build_reranker_credential(
        credential_type,
        access_key_id=_string(values.get("access_key_id")),
        secret_access_key=_string(values.get("secret_access_key")),
    )


def _required(value: str | None, field: str) -> str:
    normalized = value.strip() if value is not None else ""
    if not normalized:
        raise RerankerCredentialError(field)
    return normalized


def _string(value: object) -> str | None:
    return value if isinstance(value, str) else None
