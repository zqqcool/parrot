from __future__ import annotations

import json
from typing import cast

from app.core.redaction import is_sensitive_key, redact_sensitive_text

_MAX_MODEL_RESULT_CHARS = 12_000
_MAX_STRING_CHARS = 2_000
_MAX_LIST_ITEMS = 20
_MAX_MAPPING_ITEMS = 80
_MAX_DEPTH = 5
_CONTROL_KEYS = (
    "status",
    "code",
    "message",
    "summary",
    "error",
    "details",
    "citations",
    "citation_ids",
    "content",
    "evidence",
)


def tool_result_message(result: dict[str, object]) -> str:
    """Return a bounded, redacted tool result suitable for the next model turn."""

    public = {key: value for key, value in result.items() if not key.startswith("_")}
    compacted = _compact_mapping(public, depth=0)
    rendered = _render(compacted)
    if len(rendered) <= _MAX_MODEL_RESULT_CHARS:
        return rendered
    fallback = {key: compacted[key] for key in _CONTROL_KEYS if key in compacted}
    fallback["model_context_truncated"] = True
    fallback_rendered = _render(fallback)
    if len(fallback_rendered) <= _MAX_MODEL_RESULT_CHARS:
        return fallback_rendered
    minimal = {
        key: compacted[key]
        for key in ("status", "code", "message", "summary", "citations", "citation_ids")
        if key in compacted
    }
    minimal["model_context_truncated"] = True
    return _render(minimal)


def _compact_mapping(value: dict[str, object], *, depth: int) -> dict[str, object]:
    if depth >= _MAX_DEPTH:
        return {"model_context_truncated": True, "omitted_keys": len(value)}
    ordered = [key for key in _CONTROL_KEYS if key in value]
    ordered.extend(key for key in value if key not in ordered)
    compacted: dict[str, object] = {}
    for key in ordered[:_MAX_MAPPING_ITEMS]:
        compacted[key] = _compact_value(value[key], depth=depth + 1, key=key)
    if len(ordered) > _MAX_MAPPING_ITEMS:
        compacted["model_context_omitted_keys"] = len(ordered) - _MAX_MAPPING_ITEMS
    return compacted


def _compact_value(value: object, *, depth: int, key: str | None = None) -> object:
    if key is not None and is_sensitive_key(key):
        return "[REDACTED]"
    if isinstance(value, str):
        redacted = redact_sensitive_text(value)
        if len(redacted) <= _MAX_STRING_CHARS:
            return redacted
        return f"{redacted[:_MAX_STRING_CHARS]}\n...[truncated_for_model]"
    if isinstance(value, dict):
        return _compact_mapping(cast(dict[str, object], value), depth=depth)
    if isinstance(value, list):
        items = cast(list[object], value)
        shown = [_compact_value(item, depth=depth + 1) for item in items[:_MAX_LIST_ITEMS]]
        if len(items) > _MAX_LIST_ITEMS:
            shown.append({"model_context_omitted_items": len(items) - _MAX_LIST_ITEMS})
        return shown
    return value


def _render(value: dict[str, object]) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)
