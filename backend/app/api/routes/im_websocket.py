from __future__ import annotations

import asyncio
from datetime import datetime
from http.cookies import SimpleCookie

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.api.dependencies import verify_origin
from app.core.config import AppConfig
from app.core.error_messages import public_error_message
from app.core.errors import AppError
from app.core.ids import new_id
from app.infrastructure.redis import RedisEventSubscriber
from app.modules.anonymous.service import AnonymousSessionService
from app.modules.im.entry_service import WebsocketEntryService
from app.modules.im.service import ImChannelService, PublicWebsocketChannel
from app.modules.interactions.event_store import InteractionEventStore
from app.modules.interactions.event_visibility import is_public_interaction_event
from app.modules.interactions.pending_action_command import resolve_pending_action_command
from app.modules.interactions.runtime import RuntimeControlRequest
from app.modules.interactions.runtime_factory import build_profile_resolver
from app.modules.interactions.schemas import ImEnvelope
from app.modules.interactions.service import InteractionService

router = APIRouter()
_SUBPROTOCOL = "parrot.im.v1"


@router.websocket("/ws/{channel_key}")
async def websocket_channel(websocket: WebSocket, channel_key: str) -> None:
    try:
        channel, visitor_id, cookie = await _open_channel(websocket, channel_key)
    except AppError:
        await websocket.close(code=1008)
        return
    await websocket.accept(
        subprotocol=_SUBPROTOCOL,
        headers=websocket_cookie_headers(websocket.app.state.settings, cookie),
    )
    try:
        await _serve_channel(websocket, channel, visitor_id)
    except (ValidationError, ValueError):
        await websocket.close(code=1007)
    except WebSocketDisconnect:
        return


async def _serve_channel(
    websocket: WebSocket, channel: PublicWebsocketChannel, visitor_id: str
) -> None:
    await websocket.send_json(
        _envelope(
            "connection.ready", new_id("request_ws"), None, 0, {"channel_id": channel.channel_id}
        )
    )
    while True:
        command = ImEnvelope.model_validate(await websocket.receive_json())
        if command.type == "ping":
            await websocket.send_json(_envelope("pong", command.request_id, None, 0, {}))
        elif command.type == "interaction.subscribe" and command.interaction_id:
            await _subscribe(websocket, channel, visitor_id, command)
        elif command.type == "interaction.create":
            await _create_interaction(websocket, channel, visitor_id, command)
        else:
            await _send_error(websocket, command.request_id, "IM_COMMAND_UNSUPPORTED")


async def _subscribe(
    websocket: WebSocket,
    channel: PublicWebsocketChannel,
    visitor_id: str,
    command: ImEnvelope,
) -> None:
    if command.interaction_id is None:
        return
    try:
        await _stream_interaction(
            websocket, channel, visitor_id, command.interaction_id, command.sequence or 0
        )
    except AppError as error:
        await _send_error(websocket, command.request_id, error.code)


async def _create_interaction(
    websocket: WebSocket,
    channel: PublicWebsocketChannel,
    visitor_id: str,
    command: ImEnvelope,
) -> None:
    try:
        interaction = await _submit(websocket, channel, visitor_id, command)
        await websocket.send_json(
            _envelope(
                "interaction.accepted",
                command.request_id,
                interaction.interaction_id,
                0,
                {"status": interaction.status},
            )
        )
        await _stream_interaction(websocket, channel, visitor_id, interaction.interaction_id, 0)
    except AppError as error:
        await _send_error(websocket, command.request_id, error.code)


async def _open_channel(
    websocket: WebSocket, channel_key: str
) -> tuple[PublicWebsocketChannel, str, str | None]:
    if _SUBPROTOCOL not in websocket.scope.get("subprotocols", []):
        raise AppError("IM_PROTOCOL_INVALID", "WebSocket subprotocol is required", 400)
    async with websocket.app.state.database.session() as session:
        service = ImChannelService(session, websocket.app.state.database)
        channel = await service.resolve_websocket_channel(channel_key)
        _verify_channel_origin(websocket, channel)
        visitor = await AnonymousSessionService(
            session, websocket.app.state.settings, websocket.app.state.database
        ).resolve(
            websocket.cookies.get(websocket.app.state.settings.security.visitor_cookie_name),
            channel.tenant_id,
        )
    return channel, visitor.session.id, visitor.raw_token if visitor.is_new else None


def _verify_channel_origin(websocket: WebSocket, channel: PublicWebsocketChannel) -> None:
    origin = websocket.headers.get("origin")
    if origin is None:
        raise AppError("ORIGIN_INVALID", "Origin validation failed", 403)
    verify_origin(websocket.app.state.settings, origin)
    if origin not in channel.allowed_origins:
        raise AppError("ORIGIN_INVALID", "Origin validation failed", 403)


def websocket_cookie_headers(
    settings: AppConfig, raw_token: str | None
) -> list[tuple[bytes, bytes]]:
    if raw_token is None:
        return []
    security = settings.security
    anonymous = settings.anonymous
    cookie = SimpleCookie()
    cookie[security.visitor_cookie_name] = raw_token
    morsel = cookie[security.visitor_cookie_name]
    morsel["max-age"] = str(anonymous.session_ttl_seconds)
    morsel["path"] = "/"
    morsel["httponly"] = True
    morsel["samesite"] = "Lax"
    if security.secure_cookies:
        morsel["secure"] = True
    return [(b"set-cookie", cookie.output(header="").strip().encode())]


async def _submit(
    websocket: WebSocket,
    channel: PublicWebsocketChannel,
    visitor_id: str,
    command: ImEnvelope,
):
    text = command.data.get("text")
    if not isinstance(text, str):
        raise ValueError("interaction.create requires text")
    async with websocket.app.state.database.session() as session:
        return await WebsocketEntryService(
            session,
            websocket.app.state.database,
            websocket.app.state.runtime,
            websocket.app.state.settings,
            websocket.app.state.redis,
            build_profile_resolver(websocket.app.state.settings, session),
        ).submit(
            channel,
            visitor_id,
            command.request_id,
            command.message_id,
            text,
            websocket.client.host if websocket.client else "unknown",
        )


async def _stream_interaction(
    websocket: WebSocket,
    channel: PublicWebsocketChannel,
    visitor_id: str,
    interaction_id: str,
    sequence: int,
) -> None:
    subscriber = await websocket.app.state.redis.subscribe_interaction(interaction_id)
    try:
        while True:
            sequence, completed = await _deliver_events(
                websocket, channel, visitor_id, interaction_id, sequence
            )
            if completed:
                return
            raw = await _receive_or_notification(websocket, subscriber)
            if raw is None:
                continue
            sequence = await _handle_stream_command(
                websocket,
                channel,
                visitor_id,
                interaction_id,
                sequence,
                ImEnvelope.model_validate(raw),
            )
    finally:
        await subscriber.close()


async def _deliver_events(
    websocket: WebSocket,
    channel: PublicWebsocketChannel,
    visitor_id: str,
    interaction_id: str,
    sequence: int,
) -> tuple[int, bool]:
    for event in await _events(websocket, channel, visitor_id, interaction_id):
        if event.sequence <= sequence:
            continue
        sequence = event.sequence
        if not is_public_interaction_event(event.type):
            continue
        await websocket.send_json(
            _envelope(
                event.type,
                event.request_id,
                interaction_id,
                event.sequence,
                event.data,
                event.event_id,
                event.occurred_at,
            )
        )
        if is_terminal_event(event.type, event.data):
            return sequence, True
    return sequence, False


def is_terminal_event(event_type: str, data: dict[str, object]) -> bool:
    return event_type in {
        "ai.output.completed",
        "ai.output.failed",
        "ai.output.cancelled",
    } and data.get("runtime_status") not in {"waiting_user_input", "waiting_user_action"}


async def _handle_stream_command(
    websocket: WebSocket,
    channel: PublicWebsocketChannel,
    visitor_id: str,
    interaction_id: str,
    sequence: int,
    command: ImEnvelope,
) -> int:
    if command.type == "ping":
        await websocket.send_json(
            _envelope("pong", command.request_id, interaction_id, sequence, {})
        )
    elif command.type == "interaction.ack":
        sequence = max(sequence, command.sequence or 0)
    elif command.type in {
        "interaction.cancel",
        "interaction.steer",
        "interaction.approve",
        "interaction.reject",
    }:
        try:
            await _control(websocket, channel, visitor_id, interaction_id, command)
        except AppError as error:
            await _send_error(websocket, command.request_id, error.code)
    else:
        await _send_error(websocket, command.request_id, "IM_COMMAND_UNSUPPORTED")
    return sequence


async def _events(
    websocket: WebSocket,
    channel: PublicWebsocketChannel,
    visitor_id: str,
    interaction_id: str,
):
    async with websocket.app.state.database.session() as session:
        service = InteractionService(
            session,
            websocket.app.state.database,
            websocket.app.state.runtime,
            websocket.app.state.redis,
        )
        interaction = await service.get_owned(
            interaction_id, channel.tenant_id, "anonymous", visitor_id
        )
        if interaction.im_channel_id != channel.channel_id:
            raise AppError("AI_INTERACTION_NOT_FOUND", "Interaction not found", 404)
        return await service.list_events(interaction_id, channel.tenant_id, "anonymous", visitor_id)


async def _control(
    websocket: WebSocket,
    channel: PublicWebsocketChannel,
    visitor_id: str,
    interaction_id: str,
    command: ImEnvelope,
) -> None:
    async with websocket.app.state.database.session() as session:
        service = InteractionService(
            session,
            websocket.app.state.database,
            websocket.app.state.runtime,
            websocket.app.state.redis,
        )
        interaction = await service.get_owned(
            interaction_id, channel.tenant_id, "anonymous", visitor_id
        )
        if interaction.im_channel_id != channel.channel_id:
            raise AppError("AI_INTERACTION_NOT_FOUND", "Interaction not found", 404)
    if command.type in {"interaction.approve", "interaction.reject"}:
        await resolve_pending_action_command(
            database=websocket.app.state.database,
            dispatcher=websocket.app.state.task_dispatcher,
            notifier=websocket.app.state.redis,
            tenant_id=channel.tenant_id,
            interaction_id=interaction_id,
            actor_type="anonymous",
            actor_id=visitor_id,
            command_type=command.type,
            data=command.data,
            request_id=command.request_id,
        )
        return
    message = command.data.get("message")
    control = RuntimeControlRequest(
        interaction_id=interaction_id,
        tenant_id=channel.tenant_id,
        actor_type="anonymous",
        actor_id=visitor_id,
        execution_id=interaction.runtime_execution_id,
        request_id=command.request_id,
        message=message if isinstance(message, str) else None,
        resume_from_waiting=interaction.status == "waiting_user_input",
    )
    events = InteractionEventStore(websocket.app.state.database, websocket.app.state.redis)
    if command.type == "interaction.cancel":
        await websocket.app.state.runtime.cancel(control, events)
    else:
        await websocket.app.state.runtime.steer(control, events)


async def _receive_or_notification(
    websocket: WebSocket, subscriber: RedisEventSubscriber
) -> object | None:
    receive_task = asyncio.create_task(websocket.receive_json())
    notification_task = asyncio.create_task(subscriber.wait(15.0))
    done, pending = await asyncio.wait(
        {receive_task, notification_task}, return_when=asyncio.FIRST_COMPLETED
    )
    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)
    return receive_task.result() if receive_task in done else None


def _envelope(
    event_type: str,
    request_id: str,
    interaction_id: str | None,
    sequence: int,
    data: dict[str, object],
    message_id: str | None = None,
    occurred_at: datetime | None = None,
) -> dict[str, object]:
    return ImEnvelope(
        type=event_type,
        message_id=message_id or new_id("message"),
        request_id=request_id,
        interaction_id=interaction_id,
        sequence=sequence,
        occurred_at=occurred_at,
        data=data,
    ).model_dump(mode="json")


async def _send_error(websocket: WebSocket, request_id: str, code: str) -> None:
    await websocket.send_json(
        _envelope(
            "error",
            request_id,
            None,
            0,
            {"code": code, "message": public_error_message(code)},
        )
    )
