from __future__ import annotations

from typing import cast

_STATUSES = frozenset({"pending", "in_progress", "completed", "cancelled"})
_MAX_ITEMS = 20


def update_todos(items: list[dict[str, str]], arguments: dict[str, object]) -> dict[str, object]:
    raw_items = arguments.get("todos")
    if raw_items is None:
        return _result(items)
    if not isinstance(raw_items, list):
        return _rejected("TODO_ITEMS_INVALID")
    values = cast(list[object], raw_items)
    if len(values) > _MAX_ITEMS:
        return _rejected("TODO_ITEMS_INVALID")
    incoming = tuple(_item(value) for value in values)
    if any(item is None for item in incoming):
        return _rejected("TODO_ITEM_INVALID")
    normalized = cast(tuple[dict[str, str], ...], incoming)
    if len({item["id"] for item in normalized}) != len(normalized):
        return _rejected("TODO_DUPLICATE_ID")
    if arguments.get("merge") is True:
        merged = {item["id"]: item for item in items}
        merged.update({item["id"]: item for item in normalized})
        next_items = list(merged.values())
    else:
        next_items = list(normalized)
    if sum(item["status"] == "in_progress" for item in next_items) > 1:
        return _rejected("TODO_MULTIPLE_IN_PROGRESS")
    items[:] = next_items
    return _result(items)


def _item(value: object) -> dict[str, str] | None:
    if not isinstance(value, dict):
        return None
    raw = cast(dict[str, object], value)
    item_id = _text(raw.get("id"), 64)
    content = _text(raw.get("content"), 500)
    status = _text(raw.get("status"), 32)
    if not item_id or not content or status not in _STATUSES:
        return None
    return {"id": item_id, "content": content, "status": status}


def _text(value: object, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    normalized = value.strip()
    return normalized if len(normalized) <= limit else ""


def _result(items: list[dict[str, str]]) -> dict[str, object]:
    summary = {status: sum(item["status"] == status for item in items) for status in _STATUSES}
    return {"status": "ok", "todos": list(items), "summary": {"total": len(items), **summary}}


def _rejected(code: str) -> dict[str, object]:
    return {"status": "rejected", "code": code}
