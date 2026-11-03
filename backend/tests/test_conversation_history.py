from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.session import DatabaseManager
from app.modules.interactions.event_store import (
    InteractionEventStore,
    persist_interaction_event_message,
)
from app.modules.interactions.history import (
    ConversationHistoryContext,
    SqlConversationHistory,
    bounded_turns,
)
from app.modules.interactions.models import ConversationMessage, Interaction


class EventStoreDatabase:
    def __init__(self, session: object) -> None:
        self._session = session

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[object]:
        yield self._session

    async def set_tenant(self, session: object, tenant_id: str) -> None:
        del session, tenant_id


def test_history_groups_messages_into_ordered_turns() -> None:
    rows = (
        cast(
            ConversationMessage,
            SimpleNamespace(
                interaction_id="interaction_latest",
                role="assistant",
                content="latest response",
                created_at=datetime(2026, 7, 19, 9, 1, tzinfo=UTC),
            ),
        ),
        cast(
            ConversationMessage,
            SimpleNamespace(
                interaction_id="interaction_latest",
                role="user",
                content="latest question",
                created_at=datetime(2026, 7, 19, 9, 0, tzinfo=UTC),
            ),
        ),
        cast(
            ConversationMessage,
            SimpleNamespace(
                interaction_id="interaction_older",
                role="user",
                content="older question",
                created_at=datetime(2026, 7, 18, 8, 0, tzinfo=UTC),
            ),
        ),
    )

    history = bounded_turns(rows, max_tokens=100)

    assert [(item.user_content, item.assistant_content, item.status) for item in history] == [
        ("older question", None, "incomplete"),
        ("latest question", "latest response", "completed"),
    ]
    assert history[0].user_occurred_at == datetime(2026, 7, 18, 8, 0, tzinfo=UTC)
    assert history[1].user_occurred_at == datetime(2026, 7, 19, 9, 0, tzinfo=UTC)
    assert history[1].assistant_occurred_at == datetime(2026, 7, 19, 9, 1, tzinfo=UTC)


def test_history_budget_never_skips_a_newer_turn_for_an_older_one() -> None:
    rows = (
        cast(
            ConversationMessage,
            SimpleNamespace(
                interaction_id="interaction_latest",
                role="user",
                content="latest request requires more context than the budget allows",
                created_at=datetime(2026, 7, 19, 9, 0, tzinfo=UTC),
            ),
        ),
        cast(
            ConversationMessage,
            SimpleNamespace(
                interaction_id="interaction_older",
                role="user",
                content="older request",
                created_at=datetime(2026, 7, 18, 8, 0, tzinfo=UTC),
            ),
        ),
    )

    history = bounded_turns(rows, max_tokens=4)

    assert len(history) == 1
    assert history[0].interaction_id == "interaction_latest"
    assert history[0].user_content.endswith("…")


def test_history_keeps_each_clarification_exchange_from_one_interaction() -> None:
    rows = (
        cast(
            ConversationMessage,
            SimpleNamespace(
                interaction_id="interaction_test",
                sequence=7,
                role="assistant",
                content="Final answer",
                created_at=datetime(2026, 7, 20, 9, 3, tzinfo=UTC),
            ),
        ),
        cast(
            ConversationMessage,
            SimpleNamespace(
                interaction_id="interaction_test",
                sequence=6,
                role="user",
                content="Shanghai",
                created_at=datetime(2026, 7, 20, 9, 2, tzinfo=UTC),
            ),
        ),
        cast(
            ConversationMessage,
            SimpleNamespace(
                interaction_id="interaction_test",
                sequence=5,
                role="assistant",
                content="Which city?",
                created_at=datetime(2026, 7, 20, 9, 1, tzinfo=UTC),
            ),
        ),
        cast(
            ConversationMessage,
            SimpleNamespace(
                interaction_id="interaction_test",
                sequence=0,
                role="user",
                content="Book a hotel",
                created_at=datetime(2026, 7, 20, 9, 0, tzinfo=UTC),
            ),
        ),
    )

    history = bounded_turns(rows, max_tokens=100)

    assert [(item.user_content, item.assistant_content) for item in history] == [
        ("Book a hotel", "Which city?"),
        ("Shanghai", "Final answer"),
    ]


@pytest.mark.asyncio
async def test_resume_transcript_loads_all_messages_before_latest_user_answer() -> None:
    rows = (
        cast(
            ConversationMessage,
            SimpleNamespace(
                interaction_id="interaction_test",
                sequence=0,
                role="user",
                content="Book a hotel",
                created_at=datetime(2026, 7, 20, 9, 0, tzinfo=UTC),
            ),
        ),
        cast(
            ConversationMessage,
            SimpleNamespace(
                interaction_id="interaction_test",
                sequence=5,
                role="assistant",
                content="Which city?",
                created_at=datetime(2026, 7, 20, 9, 1, tzinfo=UTC),
            ),
        ),
        cast(
            ConversationMessage,
            SimpleNamespace(
                interaction_id="interaction_test",
                sequence=6,
                role="user",
                content="Shanghai",
                created_at=datetime(2026, 7, 20, 9, 2, tzinfo=UTC),
            ),
        ),
        cast(
            ConversationMessage,
            SimpleNamespace(
                interaction_id="interaction_test",
                sequence=9,
                role="assistant",
                content="Which date?",
                created_at=datetime(2026, 7, 20, 9, 3, tzinfo=UTC),
            ),
        ),
    )
    session = SimpleNamespace(scalars=AsyncMock(return_value=rows))
    history = SqlConversationHistory(cast(DatabaseManager, EventStoreDatabase(session)))

    messages = await history.resume_messages(
        ConversationHistoryContext(
            tenant_id="tenant_test",
            agent_id="agent_test",
            actor_type="anonymous",
            actor_id="visitor_test",
            interaction_id="interaction_test",
            conversation_id="conversation_test",
        ),
        through_sequence=9,
        max_tokens=100,
    )

    assert [(item.role, item.content) for item in messages] == [
        ("user", "Book a hotel"),
        ("assistant", "Which city?"),
        ("user", "Shanghai"),
        ("assistant", "Which date?"),
    ]


@pytest.mark.asyncio
async def test_completed_root_output_is_persisted_as_an_assistant_message() -> None:
    session = SimpleNamespace(add=Mock(), flush=AsyncMock())
    interaction = Interaction(
        id="interaction_test",
        tenant_id="tenant_test",
        agent_id="agent_test",
        actor_type="anonymous",
        actor_id="visitor_test",
        entry_type="text",
        input_type="text",
        conversation_id="conversation_test",
        runtime_depth=0,
        status="running",
    )

    await persist_interaction_event_message(
        cast(AsyncSession, session),
        interaction,
        "ai.output.completed",
        "completed",
        {"content": "Here is the answer."},
        1,
    )

    message = session.add.call_args_list[0].args[0]
    assert message.role == "assistant"
    assert message.conversation_id == "conversation_test"
    assert message.content == "Here is the answer."
    session.flush.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("event_type", "terminal_status", "data", "expected_role", "expected_content"),
    (
        (
            "ai.output.completed",
            "waiting_user_input",
            {"runtime_status": "waiting_user_input", "content": "Which city?"},
            "assistant",
            "Which city?",
        ),
        (
            "ai.interaction.steer.requested",
            "accepted",
            {"message": "Shanghai"},
            "user",
            "Shanghai",
        ),
        (
            "ai.interaction.steer.requested",
            None,
            {"message": "Keep the answer concise"},
            "user",
            "Keep the answer concise",
        ),
    ),
)
async def test_event_store_persists_clarification_messages(
    event_type: str,
    terminal_status: str | None,
    data: dict[str, object],
    expected_role: str,
    expected_content: str,
) -> None:
    interaction = Interaction(
        id="interaction_test",
        tenant_id="tenant_test",
        agent_id="agent_test",
        actor_type="anonymous",
        actor_id="visitor_test",
        entry_type="websocket",
        input_type="text",
        conversation_id="conversation_test",
        runtime_depth=0,
        status="running",
    )
    session = SimpleNamespace(
        scalar=AsyncMock(side_effect=(interaction, 4)),
        add=Mock(),
        flush=AsyncMock(),
    )

    await InteractionEventStore(cast(DatabaseManager, EventStoreDatabase(session))).append(
        tenant_id="tenant_test",
        interaction_id="interaction_test",
        request_id="request_test",
        event_type=event_type,
        data=data,
        terminal_status=terminal_status,
    )

    transcript_rows = [
        call.args[0]
        for call in session.add.call_args_list
        if isinstance(call.args[0], ConversationMessage)
    ]
    assert len(transcript_rows) == 1
    assert transcript_rows[0].role == expected_role
    assert transcript_rows[0].content == expected_content
    assert transcript_rows[0].sequence == 5
