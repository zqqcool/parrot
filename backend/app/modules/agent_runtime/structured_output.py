from __future__ import annotations

import json
from typing import cast

_MAX_STRUCTURED_OUTPUT_CHARS = 32_768
_FENCE = "```"
_ALLOWED_OPENING_FENCES = frozenset({_FENCE, f"{_FENCE}json"})


class StructuredOutputError(ValueError):
    """The model response is not one bounded JSON object."""


def decode_json_object(value: str | None) -> dict[str, object]:
    if value is None:
        raise StructuredOutputError("Structured response is missing")
    normalized = value.strip()
    if not normalized or len(normalized) > _MAX_STRUCTURED_OUTPUT_CHARS:
        raise StructuredOutputError("Structured response size is invalid")
    if normalized.startswith(_FENCE):
        normalized = _unwrap_json_fence(normalized)
    try:
        decoded = json.loads(normalized)
    except json.JSONDecodeError as error:
        raise StructuredOutputError("Structured response is not valid JSON") from error
    if not isinstance(decoded, dict):
        raise StructuredOutputError("Structured response must be a JSON object")
    return cast(dict[str, object], decoded)


def _unwrap_json_fence(value: str) -> str:
    lines = value.splitlines()
    if (
        len(lines) < 3
        or lines[0].strip().casefold() not in _ALLOWED_OPENING_FENCES
        or lines[-1].strip() != _FENCE
    ):
        raise StructuredOutputError("Structured response fence is invalid")
    inner = "\n".join(lines[1:-1]).strip()
    if not inner or _FENCE in inner:
        raise StructuredOutputError("Structured response fence is invalid")
    return inner
