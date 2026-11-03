from __future__ import annotations

from typing import cast


def payload_string(payload: dict[str, object], key: str) -> str | None:
    value = payload.get(key)
    return value if isinstance(value, str) else None


def payload_mapping(payload: dict[str, object], key: str) -> dict[str, object] | None:
    value = payload.get(key)
    if not isinstance(value, dict):
        return None
    raw = cast(dict[object, object], value)
    return {item_key: item for item_key, item in raw.items() if isinstance(item_key, str)}


def payload_mapping_tuple(payload: dict[str, object], key: str) -> tuple[dict[str, object], ...]:
    value = payload.get(key)
    if not isinstance(value, list):
        return ()
    result: list[dict[str, object]] = []
    for item in cast(list[object], value):
        if not isinstance(item, dict):
            return ()
        raw = cast(dict[object, object], item)
        result.append(
            {item_key: nested for item_key, nested in raw.items() if isinstance(item_key, str)}
        )
    return tuple(result)
