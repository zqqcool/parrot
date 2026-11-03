from __future__ import annotations

import re
from typing import Literal

from app.modules.agent_runtime.contracts import ChatMessage, ToolCall

KnowledgeRepeatReason = Literal["exact_repeat", "similar_repeat"]


def repeated_knowledge_search(
    messages: tuple[ChatMessage, ...] | list[ChatMessage],
    call: ToolCall,
    *,
    exclude_call_ids: frozenset[str] = frozenset(),
    exact_limit: int = 1,
    similar_limit: int = 2,
    similarity_threshold: float = 0.6,
) -> KnowledgeRepeatReason | None:
    """Block redundant knowledge_search queries within one interaction loop."""
    if call.name != "knowledge_search":
        return None
    query = _query(call.arguments)
    if not query:
        return None
    prior = tuple(_prior_queries(messages, exclude_call_ids | {call.id}))
    if sum(item == query for item in prior) >= exact_limit:
        return "exact_repeat"
    if sum(_similarity(item, query) >= similarity_threshold for item in prior) >= similar_limit:
        return "similar_repeat"
    return None


def knowledge_repetition_message(reason: KnowledgeRepeatReason) -> str:
    if reason == "exact_repeat":
        return (
            "The same knowledge_search query was already attempted. Use the existing evidence "
            "or answer with current limitations instead of repeating it."
        )
    return (
        "Highly similar knowledge_search queries were already attempted. Synthesize current "
        "evidence or change the query intent instead of retrying with cosmetic wording."
    )


def _prior_queries(
    messages: tuple[ChatMessage, ...] | list[ChatMessage],
    exclude_call_ids: frozenset[str],
) -> list[str]:
    queries: list[str] = []
    for message in messages:
        if message.role != "assistant":
            continue
        for tool_call in message.tool_calls:
            if tool_call.name != "knowledge_search" or tool_call.id in exclude_call_ids:
                continue
            query = _query(tool_call.arguments)
            if query:
                queries.append(query)
    return queries


def _query(arguments: dict[str, object]) -> str:
    return re.sub(r"\s+", " ", str(arguments.get("query") or "").strip().casefold())


def _similarity(left: str, right: str) -> float:
    if left == right:
        return 1.0
    left_tokens = set(_tokens(left))
    right_tokens = set(_tokens(right))
    if not left_tokens or not right_tokens:
        return 0.0
    overlap = len(left_tokens & right_tokens)
    return overlap / max(min(len(left_tokens), len(right_tokens)), 1)


def _tokens(value: str) -> list[str]:
    return [token for token in re.split(r"[^\w\u4e00-\u9fff]+", value) if len(token) >= 2]
