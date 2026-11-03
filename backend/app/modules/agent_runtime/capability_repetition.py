from __future__ import annotations

import json
import re
from typing import cast


def repeated_capability_execute(
    history: list[dict[str, object]],
    arguments: dict[str, object],
    *,
    exact_limit: int,
    similar_limit: int,
    similarity_threshold: float,
) -> str | None:
    fingerprint = _fingerprint(arguments)
    if sum(_fingerprint(item) == fingerprint for item in history) >= exact_limit:
        return "exact_repeat"
    similar = sum(
        _similarity(item, arguments) >= similarity_threshold
        for item in history
        if _capability_id(item) == _capability_id(arguments)
    )
    if similar >= similar_limit:
        return "similar_repeat"
    return None


def repetition_message(reason: str) -> str:
    if reason == "exact_repeat":
        return (
            "The same capability execution was already attempted. Use its result, change the "
            "input, or answer with the current limitations instead of repeating it."
        )
    return (
        "Highly similar capability executions were already attempted. Synthesize the current "
        "results or change strategy instead of retrying with cosmetic input changes."
    )


def _fingerprint(arguments: dict[str, object]) -> str:
    payload = arguments.get("input")
    normalized = cast(dict[str, object], payload) if isinstance(payload, dict) else {}
    return (
        f"{_capability_id(arguments)}|{json.dumps(normalized, ensure_ascii=False, sort_keys=True)}"
    )


def _similarity(left: dict[str, object], right: dict[str, object]) -> float:
    left_payload = _payload(left)
    right_payload = _payload(right)
    left_query = _query(left_payload)
    right_query = _query(right_payload)
    if not left_query or not right_query:
        return 1.0 if _fingerprint(left) == _fingerprint(right) else 0.0
    if left_query == right_query:
        return 1.0
    left_tokens = set(_tokens(left_query))
    right_tokens = set(_tokens(right_query))
    if not left_tokens or not right_tokens:
        return 0.0
    overlap = len(left_tokens & right_tokens)
    return overlap / max(min(len(left_tokens), len(right_tokens)), 1)


def _capability_id(arguments: dict[str, object]) -> str:
    return str(arguments.get("capability_id") or arguments.get("skill_id") or "").strip()


def _payload(arguments: dict[str, object]) -> dict[str, object]:
    value = arguments.get("input")
    return cast(dict[str, object], value) if isinstance(value, dict) else {}


def _query(payload: dict[str, object]) -> str:
    return re.sub(r"\s+", " ", str(payload.get("query") or "").strip().casefold())


def _tokens(value: str) -> list[str]:
    return [token for token in re.split(r"[^\w\u4e00-\u9fff]+", value) if len(token) >= 2]
