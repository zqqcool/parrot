from __future__ import annotations

import json
from typing import cast

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

_FORBIDDEN_KEYWORDS = frozenset(
    {"$ref", "$dynamicRef", "allOf", "anyOf", "oneOf", "not", "patternProperties"}
)
_MAX_SCHEMA_BYTES = 8 * 1024


def bounded_result_schema(value: object) -> dict[str, object]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("subagent result schema is invalid")
    schema = cast(dict[str, object], value)
    if not schema:
        return {}
    if schema.get("type") != "object" or _contains_forbidden_keyword(schema):
        raise ValueError("subagent result schema is invalid")
    encoded = json.dumps(schema, ensure_ascii=False, separators=(",", ":")).encode()
    if len(encoded) > _MAX_SCHEMA_BYTES:
        raise ValueError("subagent result schema is too large")
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as error:
        raise ValueError("subagent result schema is invalid") from error
    return schema


def _contains_forbidden_keyword(value: object) -> bool:
    if isinstance(value, dict):
        raw = cast(dict[object, object], value)
        return any(
            key in _FORBIDDEN_KEYWORDS or _contains_forbidden_keyword(item)
            for key, item in raw.items()
        )
    if isinstance(value, list):
        return any(_contains_forbidden_keyword(item) for item in cast(list[object], value))
    return False
