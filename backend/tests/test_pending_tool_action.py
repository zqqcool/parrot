from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest
from _agent_runtime_support import CapturingEvents, request

from app.core.clock import Clock
from app.core.errors import AppError
from app.core.task_dispatch import TaskDispatcher
from app.infrastructure.db.session import DatabaseManager
from app.modules.agent_runtime.contracts import ChatMessage, ToolCall
from app.modules.agent_runtime.output import emit_waiting_for_action
from app.modules.agent_runtime.pending_action import SqlPendingToolActionStore
from app.modules.agent_runtime.pending_action_control import PendingToolActionController
from app.modules.interactions.event_store import InteractionEventNotifier
from app.modules.interactions.models import Interaction, InteractionEvent


class _Database:
    def __init__(self, session: SimpleNamespace) -> None:
        self._session = session
        self.set_tenant = AsyncMock()

    @asynccontextmanager
    async def session(self):
        yield self._session


def _clock(now: datetime) -> Clock:
    return cast(Clock, SimpleNamespace(now=Mock(return_value=now)))


def _interaction(*, payload: dict[str, object] | None = None) -> Interaction:
    return Interaction(
        id="interaction_test",
        tenant_id="tenant_test",
        agent_id="agent_test",
        actor_type="anonymous",
        actor_id="visitor_test",
        entry_type="text",
        input_type="text",
        status="running",
        input_payload=payload or {},
    )


@pytest.mark.asyncio
async def test_pending_action_persists_private_parameters_but_returns_only_safe_controls() -> None:
    interaction = _interaction()
    session = SimpleNamespace(scalar=AsyncMock(return_value=interaction), flush=AsyncMock())
    database = _Database(session)
    store = SqlPendingToolActionStore(
        cast(DatabaseManager, database),
        _clock(datetime(2026, 7, 19, tzinfo=UTC)),
    )
    messages = [
        ChatMessage(role="system", content="root policy"),
        ChatMessage(role="assistant", content="observation", reasoning_content="private"),
        ChatMessage(
            role="assistant",
            content=None,
            tool_calls=(ToolCall(id="call_create", name="capability_execute", arguments={}),),
        ),
    ]

    public = await store.prepare(
        request(),
        ToolCall(id="call_create", name="capability_execute", arguments={}),
        {
            "pending_action": {
                "capability_id": "mcp:ticket:create",
                "server_id": "ticket",
                "tool_name": "create",
                "arguments": {"title": "Incident"},
                "schema_hash": "sha256:schema",
                "effect": "side_effect",
                "approval": "required",
            }
        },
        messages,
    )

    action = cast(dict[str, object], interaction.input_payload["pending_tool_action"])
    assert public["status"] == "waiting_approval"
    assert "capability_id" not in public
    assert "arguments" not in public
    assert action["arguments"] == {"title": "Incident"}
    assert action["actor_id"] == "visitor_test"
    snapshot = cast(list[dict[str, object]], action["resume_messages"])
    assert len(snapshot) == 2
    assert all("reasoning_content" not in message for message in snapshot)


@pytest.mark.asyncio
async def test_waiting_action_event_does_not_expose_tool_or_parameters() -> None:
    events = CapturingEvents()

    await emit_waiting_for_action(
        request(),
        events,
        {
            "action_id": "pending_1",
            "action_hash": "sha256:action",
            "version": "v1",
            "tool_name": "create_ticket",
            "arguments": {"secret": "private"},
        },
    )

    data = events.items[-1][1]
    assert data["runtime_status"] == "waiting_user_action"
    assert data["action"] == {
        "action_id": "pending_1",
        "action_hash": "sha256:action",
        "version": "v1",
        "choices": ["approve", "reject"],
    }
    assert "create_ticket" not in str(data)
    assert "private" not in str(data)


@pytest.mark.asyncio
async def test_structured_approval_validates_identity_then_dispatches_after_commit() -> None:
    now = datetime(2026, 7, 19, tzinfo=UTC)
    action: dict[str, object] = {
        "version": "v1",
        "action_id": "pending_1",
        "action_hash": "sha256:action",
        "status": "pending",
        "tenant_id": "tenant_test",
        "actor_type": "anonymous",
        "actor_id": "visitor_test",
        "expires_at": (now + timedelta(minutes=10)).isoformat(),
    }
    interaction = _interaction(payload={"pending_tool_action": action})
    interaction.status = "waiting_user_action"
    session = SimpleNamespace(
        scalar=AsyncMock(side_effect=(interaction, 4)),
        add=Mock(),
        flush=AsyncMock(),
    )
    database = _Database(session)
    order: list[str] = []

    async def dispatch(*_args: object) -> None:
        order.append("dispatch")

    async def notify(*_args: object) -> None:
        order.append("notify")

    dispatcher = SimpleNamespace(dispatch_runtime=AsyncMock(side_effect=dispatch))
    notifier = SimpleNamespace(publish_interaction_event=AsyncMock(side_effect=notify))
    controller = PendingToolActionController(
        cast(DatabaseManager, database),
        cast(TaskDispatcher, dispatcher),
        cast(InteractionEventNotifier, notifier),
        _clock(now),
    )

    await controller.resolve(
        tenant_id="tenant_test",
        interaction_id="interaction_test",
        actor_type="anonymous",
        actor_id="visitor_test",
        action_id="pending_1",
        action_hash="sha256:action",
        version="v1",
        decision="approve",
        request_id="request_approve",
    )

    resolved = cast(dict[str, object], interaction.input_payload["pending_tool_action"])
    assert resolved["status"] == "approved"
    assert interaction.status == "accepted"
    event = cast(InteractionEvent, session.add.call_args.args[0])
    assert event.type == "ai.tool.approval.resolved"
    assert event.data == {
        "action_id": "pending_1",
        "decision": "approve",
        "status": "approved",
    }
    notifier.publish_interaction_event.assert_awaited_once_with("interaction_test")
    dispatcher.dispatch_runtime.assert_awaited_once_with("tenant_test", "interaction_test")
    assert order == ["dispatch", "notify"]


@pytest.mark.asyncio
async def test_structured_approval_dispatch_survives_notification_failure() -> None:
    now = datetime(2026, 7, 19, tzinfo=UTC)
    action: dict[str, object] = {
        "version": "v1",
        "action_id": "pending_1",
        "action_hash": "sha256:action",
        "status": "pending",
        "tenant_id": "tenant_test",
        "actor_type": "anonymous",
        "actor_id": "visitor_test",
        "expires_at": (now + timedelta(minutes=10)).isoformat(),
    }
    interaction = _interaction(payload={"pending_tool_action": action})
    interaction.status = "waiting_user_action"
    session = SimpleNamespace(
        scalar=AsyncMock(side_effect=(interaction, 0)),
        add=Mock(),
        flush=AsyncMock(),
    )
    dispatcher = SimpleNamespace(dispatch_runtime=AsyncMock())
    notifier = SimpleNamespace(
        publish_interaction_event=AsyncMock(side_effect=RuntimeError("redis unavailable"))
    )
    controller = PendingToolActionController(
        cast(DatabaseManager, _Database(session)),
        cast(TaskDispatcher, dispatcher),
        cast(InteractionEventNotifier, notifier),
        _clock(now),
    )

    await controller.resolve(
        tenant_id="tenant_test",
        interaction_id="interaction_test",
        actor_type="anonymous",
        actor_id="visitor_test",
        action_id="pending_1",
        action_hash="sha256:action",
        version="v1",
        decision="approve",
        request_id="request_approve",
    )

    dispatcher.dispatch_runtime.assert_awaited_once_with("tenant_test", "interaction_test")


@pytest.mark.asyncio
async def test_structured_approval_fails_closed_on_hash_mismatch() -> None:
    now = datetime(2026, 7, 19, tzinfo=UTC)
    interaction = _interaction(
        payload={
            "pending_tool_action": {
                "version": "v1",
                "action_id": "pending_1",
                "action_hash": "sha256:stored",
                "status": "pending",
                "tenant_id": "tenant_test",
                "actor_type": "anonymous",
                "actor_id": "visitor_test",
                "expires_at": (now + timedelta(minutes=10)).isoformat(),
            }
        }
    )
    interaction.status = "waiting_user_action"
    session = SimpleNamespace(scalar=AsyncMock(return_value=interaction))
    dispatcher = SimpleNamespace(dispatch_runtime=AsyncMock())
    controller = PendingToolActionController(
        cast(DatabaseManager, _Database(session)),
        cast(TaskDispatcher, dispatcher),
        clock=_clock(now),
    )

    with pytest.raises(AppError) as captured:
        await controller.resolve(
            tenant_id="tenant_test",
            interaction_id="interaction_test",
            actor_type="anonymous",
            actor_id="visitor_test",
            action_id="pending_1",
            action_hash="sha256:tampered",
            version="v1",
            decision="approve",
            request_id="request_approve",
        )

    assert captured.value.code == "AI_PENDING_ACTION_CONFLICT"
    dispatcher.dispatch_runtime.assert_not_awaited()
