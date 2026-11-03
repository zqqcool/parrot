from __future__ import annotations

from app.modules.agent_runtime.contracts import ChatMessage, ToolCall
from app.modules.agent_runtime.knowledge_retry import exhausted_no_results_retry


def test_no_results_allows_one_follow_up_search_then_rejects_another() -> None:
    messages = [
        ChatMessage(
            role="tool",
            name="knowledge_search",
            tool_call_id="initial",
            content='{"retrieval_status":"no_results"}',
        )
    ]
    call = ToolCall(id="retry_one", name="knowledge_search", arguments={"query": "release"})

    assert exhausted_no_results_retry(messages, call) is None

    messages.append(
        ChatMessage(
            role="tool",
            name="knowledge_search",
            tool_call_id=call.id,
            content='{"retrieval_status":"no_results"}',
        )
    )

    rejection = exhausted_no_results_retry(
        messages,
        ToolCall(id="retry_two", name="knowledge_search", arguments={"query": "releases"}),
    )

    assert rejection == {
        "status": "rejected",
        "code": "KNOWLEDGE_NO_RESULTS_RETRY_EXHAUSTED",
        "message": (
            "A no-results search has already been retried once; answer without claiming evidence."
        ),
    }


def test_successful_retrieval_resets_the_no_results_retry_boundary() -> None:
    messages = [
        ChatMessage(
            role="tool",
            name="knowledge_search",
            tool_call_id="first",
            content='{"retrieval_status":"no_results"}',
        ),
        ChatMessage(
            role="tool",
            name="knowledge_search",
            tool_call_id="second",
            content='{"retrieval_status":"ok"}',
        ),
    ]

    assert (
        exhausted_no_results_retry(
            messages,
            ToolCall(id="third", name="knowledge_search", arguments={"query": "release policy"}),
        )
        is None
    )
