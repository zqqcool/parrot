from __future__ import annotations

from app.modules.agent_runtime.contracts import ChatMessage, ToolCall
from app.modules.agent_runtime.knowledge_repetition import repeated_knowledge_search


def test_exact_knowledge_search_repeat_is_blocked() -> None:
    messages = (
        ChatMessage(
            role="assistant",
            content=None,
            tool_calls=(
                ToolCall(
                    id="call_1",
                    name="knowledge_search",
                    arguments={"query": "parrot 技术栈"},
                ),
            ),
        ),
    )
    reason = repeated_knowledge_search(
        messages,
        ToolCall(id="call_2", name="knowledge_search", arguments={"query": "parrot 技术栈"}),
        exclude_call_ids=frozenset({"call_2"}),
    )
    assert reason == "exact_repeat"


def test_current_turn_calls_are_excluded_from_repeat_detection() -> None:
    messages = (
        ChatMessage(
            role="assistant",
            content=None,
            tool_calls=(
                ToolCall(
                    id="call_1",
                    name="knowledge_search",
                    arguments={"query": "parrot 技术栈"},
                ),
            ),
        ),
    )
    reason = repeated_knowledge_search(
        messages,
        ToolCall(id="call_1", name="knowledge_search", arguments={"query": "parrot 技术栈"}),
        exclude_call_ids=frozenset({"call_1"}),
    )
    assert reason is None


def test_similar_knowledge_search_repeat_is_blocked_after_limit() -> None:
    messages = (
        ChatMessage(
            role="assistant",
            content=None,
            tool_calls=(
                ToolCall(
                    id="call_1",
                    name="knowledge_search",
                    arguments={"query": "parrot technology stack overview"},
                ),
            ),
        ),
        ChatMessage(
            role="assistant",
            content=None,
            tool_calls=(
                ToolCall(
                    id="call_2",
                    name="knowledge_search",
                    arguments={"query": "parrot technology stack details"},
                ),
            ),
        ),
    )
    reason = repeated_knowledge_search(
        messages,
        ToolCall(
            id="call_3",
            name="knowledge_search",
            arguments={"query": "parrot technology stack components"},
        ),
        similar_limit=2,
        similarity_threshold=0.5,
    )
    assert reason == "similar_repeat"


def test_distinct_knowledge_search_query_is_allowed() -> None:
    messages = (
        ChatMessage(
            role="assistant",
            content=None,
            tool_calls=(
                ToolCall(
                    id="call_1",
                    name="knowledge_search",
                    arguments={"query": "release policy"},
                ),
            ),
        ),
    )
    reason = repeated_knowledge_search(
        messages,
        ToolCall(id="call_2", name="knowledge_search", arguments={"query": "deployment checklist"}),
    )
    assert reason is None
