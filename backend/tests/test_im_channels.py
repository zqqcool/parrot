from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
from fastapi import WebSocket
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.im import _send_error as send_admin_error  # pyright: ignore[reportPrivateUsage]
from app.api.routes.im_websocket import (
    _deliver_events,  # pyright: ignore[reportPrivateUsage]
    _send_error,  # pyright: ignore[reportPrivateUsage]
    is_terminal_event,
    websocket_cookie_headers,
)
from app.core.agent_runtime import AgentRuntimeProfileResolver
from app.core.config import AppConfig
from app.core.errors import AppError
from app.infrastructure.db.session import DatabaseManager
from app.infrastructure.redis import RedisManager
from app.modules.agents.catalog import AgentCatalog
from app.modules.agents.ports import AgentRuntimeTarget
from app.modules.iam.schemas import PrincipalContext
from app.modules.im.channel_types import CHANNEL_TYPES, get_channel_type
from app.modules.im.entry_service import WebsocketEntryService
from app.modules.im.models import ImAgentBinding, ImChannel, ImInboundDelivery
from app.modules.im.repository import ImChannelRepository
from app.modules.im.schemas import ImChannelCreateRequest, PublicImChannelView
from app.modules.im.service import ImChannelService, PublicWebsocketChannel
from app.modules.interactions.event_visibility import is_public_interaction_event
from app.modules.interactions.runtime import RuntimePort
from app.modules.interactions.schemas import InteractionAccepted


def test_websocket_channel_requires_explicit_valid_origins() -> None:
    payload = ImChannelCreateRequest(
        name="Web widget",
        allowed_origins=("https://console.example.test/",),
    )

    assert payload.allowed_origins == ("https://console.example.test",)
    assert payload.channel_type == "websocket"
    with pytest.raises(ValidationError):
        ImChannelCreateRequest(name="Web widget", allowed_origins=())
    with pytest.raises(ValidationError):
        ImChannelCreateRequest(
            name="Web widget", allowed_origins=("https://console.example.test/path",)
        )


def test_channel_type_catalog_keeps_future_adapters_disabled() -> None:
    websocket = get_channel_type("websocket")

    assert websocket is not None and websocket.enabled
    assert {item.key for item in CHANNEL_TYPES if not item.enabled} == {
        "feishu",
        "dingtalk",
        "wecom",
    }


@pytest.mark.asyncio
async def test_channel_service_rejects_disabled_channel_type() -> None:
    database = SimpleNamespace(set_tenant=AsyncMock())
    service = ImChannelService(
        cast(AsyncSession, SimpleNamespace()), cast(DatabaseManager, database)
    )
    principal = cast(
        PrincipalContext,
        SimpleNamespace(tenant_id="tenant_1", permissions=("im.channels.manage",)),
    )
    payload = ImChannelCreateRequest(
        channel_type="feishu",
        name="Feishu bot",
        allowed_origins=("https://console.example.test",),
    )

    with pytest.raises(AppError, match="not enabled") as raised:
        await service.create_channel(principal, "tenant_1", payload)

    assert raised.value.code == "IM_CHANNEL_TYPE_UNAVAILABLE"


@pytest.mark.asyncio
async def test_channel_resolution_uses_public_binding_then_enters_tenant_scope() -> None:
    channel = ImChannel(
        id="channel_1",
        tenant_id="tenant_1",
        channel_type="websocket",
        name="Web widget",
        public_key="public_1",
        status="enabled",
        allowed_origins=["https://console.example.test"],
    )
    binding = ImAgentBinding(
        id="binding_1",
        tenant_id="tenant_1",
        channel_id=channel.id,
        agent_id="agent_1",
        status="enabled",
    )
    repository = SimpleNamespace(
        get_public_channel=AsyncMock(return_value=channel),
        get_binding=AsyncMock(return_value=binding),
    )
    agents = SimpleNamespace(
        get_anonymous_target=AsyncMock(
            return_value=AgentRuntimeTarget("agent_1", "tenant_1", "runtime_1")
        )
    )
    database = SimpleNamespace(set_tenant=AsyncMock())
    service = ImChannelService(
        cast(AsyncSession, SimpleNamespace()), cast(DatabaseManager, database)
    )
    service.repository = cast(ImChannelRepository, repository)
    service.agents = cast(AgentCatalog, agents)

    resolved = await service.resolve_websocket_channel("public_1")

    assert resolved == PublicWebsocketChannel(
        channel_id="channel_1",
        binding_id="binding_1",
        tenant_id="tenant_1",
        agent_id="agent_1",
        runtime_agent_id="runtime_1",
        allowed_origins=("https://console.example.test",),
    )
    database.set_tenant.assert_awaited_once_with(service.session, "tenant_1")
    agents.get_anonymous_target.assert_awaited_once_with("tenant_1", "agent_1")


@pytest.mark.asyncio
async def test_public_agent_channel_listing_returns_only_enabled_websocket_bindings() -> None:
    websocket = ImChannel(
        id="channel_websocket",
        tenant_id="tenant_1",
        channel_type="websocket",
        name="Web test",
        public_key="channel_websocket_key",
        status="enabled",
        allowed_origins=["https://console.example.test"],
    )
    disabled = ImChannel(
        id="channel_disabled",
        tenant_id="tenant_1",
        channel_type="websocket",
        name="Disabled test",
        public_key="channel_disabled_key",
        status="disabled",
        allowed_origins=["https://console.example.test"],
    )
    repository = SimpleNamespace(
        list_agent_bindings=AsyncMock(
            return_value=(
                (
                    ImAgentBinding(
                        id="binding_websocket",
                        tenant_id="tenant_1",
                        channel_id=websocket.id,
                        agent_id="agent_1",
                        status="enabled",
                    ),
                    websocket,
                ),
                (
                    ImAgentBinding(
                        id="binding_disabled",
                        tenant_id="tenant_1",
                        channel_id=disabled.id,
                        agent_id="agent_1",
                        status="enabled",
                    ),
                    disabled,
                ),
            )
        )
    )
    agents = SimpleNamespace(
        get_anonymous_target_by_slug=AsyncMock(
            return_value=AgentRuntimeTarget("agent_1", "tenant_1", "runtime_1")
        )
    )
    database = SimpleNamespace(set_tenant=AsyncMock())
    service = ImChannelService(
        cast(AsyncSession, SimpleNamespace()), cast(DatabaseManager, database)
    )
    service.repository = cast(ImChannelRepository, repository)
    service.agents = cast(AgentCatalog, agents)

    result = await service.list_public_agent_channels("demo")

    assert result == [
        PublicImChannelView(
            channel_key="channel_websocket_key", channel_type="websocket", name="Web test"
        )
    ]
    database.set_tenant.assert_awaited_once_with(service.session, "tenant_1")
    agents.get_anonymous_target_by_slug.assert_awaited_once_with("demo")


@pytest.mark.asyncio
async def test_websocket_entry_records_idempotency_per_visitor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded: list[ImInboundDelivery] = []

    async def record_inbound(item: ImInboundDelivery) -> None:
        database.set_tenant.assert_awaited_once_with(service.session, "tenant_1")
        recorded.append(item)

    repository = SimpleNamespace(
        inbound_by_message=AsyncMock(return_value=None),
        record_inbound=record_inbound,
    )
    accepted = InteractionAccepted(interaction_id="interaction_1", status="accepted")

    class FakeInteractionService:
        def __init__(self, *_args: object) -> None:
            pass

        async def submit(self, *_args: object) -> InteractionAccepted:
            return accepted

    monkeypatch.setattr("app.modules.im.entry_service.InteractionService", FakeInteractionService)
    database = SimpleNamespace(set_tenant=AsyncMock())
    service = WebsocketEntryService(
        cast(AsyncSession, SimpleNamespace()),
        cast(DatabaseManager, database),
        cast(RuntimePort, SimpleNamespace()),
        cast(
            AppConfig,
            SimpleNamespace(
                api=SimpleNamespace(prefix="/api/v1"),
                limits=SimpleNamespace(max_text_chars=100),
                anonymous=SimpleNamespace(rate_limit_requests=10, rate_limit_window_seconds=60),
            ),
        ),
        cast(RedisManager, SimpleNamespace(allow=AsyncMock(return_value=True))),
        cast(AgentRuntimeProfileResolver, None),
    )
    service.repository = cast(ImChannelRepository, repository)
    channel = PublicWebsocketChannel(
        channel_id="channel_1",
        binding_id="binding_1",
        tenant_id="tenant_1",
        agent_id="agent_1",
        runtime_agent_id="runtime_1",
        allowed_origins=("https://console.example.test",),
    )

    result = await service.submit(
        channel,
        "visitor_1",
        "request_1",
        "message_1",
        "hello",
        "127.0.0.1",
    )

    assert result == accepted
    repository.inbound_by_message.assert_awaited_once_with(
        "tenant_1", "channel_1", "visitor_1", "message_1"
    )
    assert recorded[0].visitor_id == "visitor_1"
    assert recorded[0].interaction_id == "interaction_1"
    database.set_tenant.assert_awaited_once_with(service.session, "tenant_1")


def test_websocket_cookie_and_terminal_semantics() -> None:
    settings = SimpleNamespace(
        security=SimpleNamespace(
            visitor_cookie_name="visitor_cookie",
            secure_cookies=True,
        ),
        anonymous=SimpleNamespace(session_ttl_seconds=600),
    )

    headers = websocket_cookie_headers(cast(AppConfig, settings), "visitor_token")

    assert headers[0][0] == b"set-cookie"
    assert b"visitor_cookie=visitor_token" in headers[0][1]
    assert b"HttpOnly" in headers[0][1]
    assert is_terminal_event("ai.output.completed", {"runtime_status": "completed"})
    assert not is_terminal_event("ai.output.completed", {"runtime_status": "waiting_user_input"})
    assert not is_terminal_event("ai.output.completed", {"runtime_status": "waiting_user_action"})


def test_public_event_policy_is_default_deny_for_agent_process_events() -> None:
    assert is_public_interaction_event("ai.output.delta")
    assert is_public_interaction_event("ai.output.completed")
    assert is_public_interaction_event("ai.thinking.delta")
    assert is_public_interaction_event("ai.thinking.completed")
    assert not is_public_interaction_event("ai.input.processed")
    assert not is_public_interaction_event("ai.agent.plan.created")
    assert not is_public_interaction_event("ai.tool.completed")
    assert not is_public_interaction_event("ai.knowledge.retrieved")
    assert not is_public_interaction_event("ai.subagent.all_completed")


@pytest.mark.asyncio
async def test_websocket_delivery_skips_agent_process_events_but_advances_sequence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    occurred_at = datetime.now(UTC)
    records: list[object] = [
        SimpleNamespace(
            sequence=1,
            type="ai.input.processed",
            request_id="req_1",
            event_id="event_1",
            occurred_at=occurred_at,
            data={"internal": "do not expose"},
        ),
        SimpleNamespace(
            sequence=2,
            type="ai.output.delta",
            request_id="req_1",
            event_id="event_2",
            occurred_at=occurred_at,
            data={"output_id": "output_1", "delta": "Hello", "delta_index": 1},
        ),
        SimpleNamespace(
            sequence=3,
            type="ai.output.completed",
            request_id="req_1",
            event_id="event_3",
            occurred_at=occurred_at,
            data={"output_id": "output_1", "content": "Hello", "runtime_status": "completed"},
        ),
    ]

    async def list_events(*_args: object) -> list[object]:
        return records

    monkeypatch.setattr("app.api.routes.im_websocket._events", list_events)
    websocket = SimpleNamespace(send_json=AsyncMock())

    sequence, completed = await _deliver_events(
        cast(WebSocket, websocket),
        cast(PublicWebsocketChannel, SimpleNamespace()),
        "visitor_1",
        "interaction_1",
        0,
    )

    assert (sequence, completed) == (3, True)
    assert [call.args[0]["type"] for call in websocket.send_json.await_args_list] == [
        "ai.output.delta",
        "ai.output.completed",
    ]


@pytest.mark.asyncio
async def test_websocket_error_includes_reviewed_chinese_message() -> None:
    for send_error in (_send_error, send_admin_error):
        websocket = SimpleNamespace(send_json=AsyncMock())

        await send_error(cast(WebSocket, websocket), "req_web_1", "SKILL_BUILD_REQUIRED")

        websocket.send_json.assert_awaited_once()
        payload = websocket.send_json.await_args.args[0]
        assert payload["type"] == "error"
        assert payload["request_id"] == "req_web_1"
        assert payload["data"] == {
            "code": "SKILL_BUILD_REQUIRED",
            "message": (
                "可执行 Skill 的草稿尚未完成当前构建，请先点击“构建草稿”，构建成功后再发布。"
            ),
        }
