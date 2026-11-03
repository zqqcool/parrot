from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from sqlalchemy import select

from app.api.dependencies import verify_origin
from app.core.clock import utc_now
from app.core.config import AppConfig
from app.core.error_messages import public_error_message
from app.core.errors import AppError
from app.core.ids import new_id
from app.infrastructure.redis import RedisEventSubscriber
from app.modules.anonymous.service import AnonymousSessionService
from app.modules.iam.permissions import INTERACTIONS_READ_ANY
from app.modules.iam.service import SessionService
from app.modules.interactions.event_store import InteractionEventStore
from app.modules.interactions.event_visibility import is_public_interaction_event
from app.modules.interactions.models import Interaction, InteractionEvent
from app.modules.interactions.pending_action_command import resolve_pending_action_command
from app.modules.interactions.runtime import RuntimeControlRequest
from app.modules.interactions.schemas import ImEnvelope
from app.modules.interactions.service import InteractionService

router = APIRouter()


@router.websocket("/admin/ws")
async def admin_im_socket(websocket: WebSocket) -> None:
    settings = websocket.app.state.settings
    protocol = websocket.query_params.get("protocol")
    if protocol != "parrot.im.v1" or not _origin_allowed(settings, websocket.headers.get("origin")):
        await websocket.close(code=1008)
        return
    authenticated = await _authenticate_admin(websocket)
    if (
        authenticated is None
        or authenticated.principal.tenant_id is None
        or INTERACTIONS_READ_ANY not in authenticated.principal.permissions
    ):
        await websocket.close(code=1008)
        return
    await websocket.accept(subprotocol=None)
    await websocket.send_json(
        _server_envelope("connection.ready", new_id("request_ws"), None, 0).model_dump(mode="json")
    )
    try:
        command = ImEnvelope.model_validate(await websocket.receive_json())
        tenant_id = authenticated.principal.tenant_id
        if (
            command.type != "interaction.subscribe"
            or not command.interaction_id
            or not await _tenant_owns_interaction(websocket, tenant_id, command.interaction_id)
        ):
            await _send_error(websocket, command.request_id, "AI_INTERACTION_NOT_FOUND")
            await websocket.close(code=1008)
            return
        await _stream_admin_interaction(websocket, tenant_id, command)
    except (ValidationError, ValueError):
        await websocket.close(code=1007)
    except WebSocketDisconnect:
        return


@router.websocket("/ws")
async def im_socket(websocket: WebSocket) -> None:
    settings = websocket.app.state.settings
    protocol = websocket.query_params.get("protocol")
    if protocol != "parrot.im.v1" or not _origin_allowed(settings, websocket.headers.get("origin")):
        await websocket.close(code=1008)
        return
    visitor = await _authenticate(websocket)
    if visitor is None:
        await websocket.close(code=1008)
        return

    await websocket.accept(subprotocol=None)
    await websocket.send_json(
        _server_envelope("connection.ready", new_id("request_ws"), None, 0).model_dump(mode="json")
    )
    try:
        command = ImEnvelope.model_validate(await websocket.receive_json())
        if command.type != "interaction.subscribe" or not command.interaction_id:
            await _send_error(websocket, command.request_id, "IM_COMMAND_INVALID")
            await websocket.close(code=1008)
            return
        if not await _owns_interaction(websocket, visitor.tenant_id, visitor.id, command):
            await _send_error(websocket, command.request_id, "AI_INTERACTION_NOT_FOUND")
            await websocket.close(code=1008)
            return
        await _stream_interaction(websocket, visitor.tenant_id, visitor.id, command)
    except (ValidationError, ValueError):
        await websocket.close(code=1007)
    except WebSocketDisconnect:
        return


async def _stream_interaction(
    websocket: WebSocket,
    tenant_id: str,
    actor_id: str,
    command: ImEnvelope,
) -> None:
    interaction_id = command.interaction_id
    if interaction_id is None:
        return
    sequence = command.sequence or 0
    subscriber = await websocket.app.state.redis.subscribe_interaction(interaction_id)
    try:
        while True:
            events = await _events_after(websocket, tenant_id, interaction_id, sequence)
            for event in events:
                sequence = event.sequence
                if not is_public_interaction_event(event.type):
                    continue
                await websocket.send_json(
                    ImEnvelope(
                        type=event.type,
                        message_id=event.id,
                        request_id=event.request_id,
                        interaction_id=interaction_id,
                        sequence=event.sequence,
                        occurred_at=event.created_at,
                        data=event.data,
                    ).model_dump(mode="json")
                )
            raw = await _receive_or_notification(websocket, subscriber)
            if raw is None:
                continue
            incoming = ImEnvelope.model_validate(raw)
            if incoming.type == "ping":
                await websocket.send_json(
                    _server_envelope(
                        "pong", incoming.request_id, interaction_id, sequence
                    ).model_dump(mode="json")
                )
            elif incoming.type == "interaction.ack":
                sequence = max(sequence, incoming.sequence or 0)
            elif incoming.type in {
                "interaction.cancel",
                "interaction.steer",
                "interaction.approve",
                "interaction.reject",
            }:
                if incoming.interaction_id not in {None, interaction_id}:
                    await _send_error(websocket, incoming.request_id, "AI_INTERACTION_NOT_FOUND")
                    continue
                await _control_runtime(
                    websocket,
                    tenant_id=tenant_id,
                    actor_id=actor_id,
                    interaction_id=interaction_id,
                    command=incoming,
                )
            else:
                await _send_error(websocket, incoming.request_id, "IM_COMMAND_UNSUPPORTED")
    finally:
        await subscriber.close()


async def _stream_admin_interaction(
    websocket: WebSocket,
    tenant_id: str,
    command: ImEnvelope,
) -> None:
    interaction_id = command.interaction_id
    if interaction_id is None:
        return
    sequence = command.sequence or 0
    subscriber = await websocket.app.state.redis.subscribe_interaction(interaction_id)
    try:
        while True:
            events = await _events_after(websocket, tenant_id, interaction_id, sequence)
            for event in events:
                sequence = event.sequence
                await websocket.send_json(
                    ImEnvelope(
                        type=event.type,
                        message_id=event.id,
                        request_id=event.request_id,
                        interaction_id=interaction_id,
                        sequence=event.sequence,
                        occurred_at=event.created_at,
                        data=event.data,
                    ).model_dump(mode="json")
                )
            raw = await _receive_or_notification(websocket, subscriber)
            if raw is None:
                continue
            incoming = ImEnvelope.model_validate(raw)
            if incoming.type == "ping":
                await websocket.send_json(
                    _server_envelope(
                        "pong", incoming.request_id, interaction_id, sequence
                    ).model_dump(mode="json")
                )
            elif incoming.type == "interaction.ack":
                sequence = max(sequence, incoming.sequence or 0)
            else:
                await _send_error(websocket, incoming.request_id, "IM_COMMAND_UNSUPPORTED")
    finally:
        await subscriber.close()


async def _receive_or_notification(
    websocket: WebSocket,
    subscriber: RedisEventSubscriber,
) -> object | None:
    receive_task = asyncio.create_task(websocket.receive_json())
    notification_task = asyncio.create_task(subscriber.wait(15.0))
    done, pending = await asyncio.wait(
        {receive_task, notification_task},
        return_when=asyncio.FIRST_COMPLETED,
    )
    for task in pending:
        task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
    if receive_task in done:
        return receive_task.result()
    return None


async def _control_runtime(
    websocket: WebSocket,
    *,
    tenant_id: str,
    actor_id: str,
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
        interaction = await service.get_owned(interaction_id, tenant_id, "anonymous", actor_id)
    if command.type in {"interaction.approve", "interaction.reject"}:
        try:
            await resolve_pending_action_command(
                database=websocket.app.state.database,
                dispatcher=websocket.app.state.task_dispatcher,
                notifier=websocket.app.state.redis,
                tenant_id=tenant_id,
                interaction_id=interaction_id,
                actor_type="anonymous",
                actor_id=actor_id,
                command_type=command.type,
                data=command.data,
                request_id=command.request_id,
            )
        except AppError as error:
            await _send_error(websocket, command.request_id, error.code)
        return
    if command.type == "interaction.steer" and interaction.status not in {
        "accepted",
        "running",
        "waiting_user_input",
    }:
        await _send_error(websocket, command.request_id, "AI_INTERACTION_NOT_STEERABLE")
        return
    message = command.data.get("message")
    control = RuntimeControlRequest(
        interaction_id=interaction_id,
        tenant_id=tenant_id,
        actor_type="anonymous",
        actor_id=actor_id,
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


async def _authenticate(websocket: WebSocket):
    settings = websocket.app.state.settings
    raw = websocket.cookies.get(settings.security.visitor_cookie_name)
    async with websocket.app.state.database.session() as session:
        return await AnonymousSessionService(
            session, settings, websocket.app.state.database
        ).authenticate(raw)


async def _authenticate_admin(websocket: WebSocket):
    settings = websocket.app.state.settings
    raw = websocket.cookies.get(settings.security.session_cookie_name)
    try:
        async with websocket.app.state.database.session() as session:
            return await SessionService(
                session, settings, websocket.app.state.database
            ).authenticate(raw, new_id("request_ws"))
    except AppError:
        return None


async def _tenant_owns_interaction(
    websocket: WebSocket, tenant_id: str, interaction_id: str
) -> bool:
    async with websocket.app.state.database.session() as session:
        await websocket.app.state.database.set_tenant(session, tenant_id)
        value = await session.scalar(
            select(Interaction.id).where(
                Interaction.tenant_id == tenant_id,
                Interaction.id == interaction_id,
            )
        )
        return value is not None


async def _owns_interaction(
    websocket: WebSocket, tenant_id: str, actor_id: str, command: ImEnvelope
):
    async with websocket.app.state.database.session() as session:
        service = InteractionService(
            session,
            websocket.app.state.database,
            websocket.app.state.runtime,
            websocket.app.state.redis,
        )
        try:
            await service.get_owned(command.interaction_id or "", tenant_id, "anonymous", actor_id)
        except AppError as error:
            if error.code == "AI_INTERACTION_NOT_FOUND":
                return False
            raise
    return True


async def _events_after(websocket: WebSocket, tenant_id: str, interaction_id: str, sequence: int):
    database = websocket.app.state.database
    async with database.session() as session:
        await database.set_tenant(session, tenant_id)
        result = await session.execute(
            select(InteractionEvent)
            .where(
                InteractionEvent.interaction_id == interaction_id,
                InteractionEvent.sequence > sequence,
            )
            .order_by(InteractionEvent.sequence)
            .limit(100)
        )
        return tuple(result.scalars())


def _origin_allowed(settings: AppConfig, origin: str | None) -> bool:
    try:
        verify_origin(settings, origin)
    except Exception:
        return False
    return True


def _server_envelope(
    event_type: str, request_id: str, interaction_id: str | None, sequence: int
) -> ImEnvelope:
    return ImEnvelope(
        type=event_type,
        message_id=new_id("message"),
        request_id=request_id,
        interaction_id=interaction_id,
        sequence=sequence,
        occurred_at=utc_now(),
        data={},
    )


async def _send_error(websocket: WebSocket, request_id: str, code: str) -> None:
    envelope = _server_envelope("error", request_id, None, 0)
    envelope.data.update({"code": code, "message": public_error_message(code)})
    await websocket.send_json(envelope.model_dump(mode="json"))
