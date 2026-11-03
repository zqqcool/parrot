from __future__ import annotations

import hashlib
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.agent_runtime import AgentRuntimeProfileResolver
from app.core.clock import utc_now
from app.core.config import AppConfig
from app.core.errors import AppError
from app.core.ids import new_id
from app.infrastructure.db.session import DatabaseManager
from app.infrastructure.redis import RedisManager
from app.modules.agents.ports import AgentRuntimeTarget
from app.modules.im.models import ImInboundDelivery
from app.modules.im.repository import ImChannelRepository
from app.modules.im.service import PublicWebsocketChannel
from app.modules.interactions.runtime import RuntimePort
from app.modules.interactions.schemas import InteractionAccepted
from app.modules.interactions.service import InteractionService, InteractionSubmission


class WebsocketEntryService:
    def __init__(
        self,
        session: AsyncSession,
        database: DatabaseManager,
        runtime: RuntimePort,
        settings: AppConfig,
        redis: RedisManager,
        profile_resolver: AgentRuntimeProfileResolver | None,
    ) -> None:
        self.session = session
        self.database = database
        self.runtime = runtime
        self.settings = settings
        self.redis = redis
        self.profile_resolver = profile_resolver
        self.repository = ImChannelRepository(session)

    async def submit(
        self,
        channel: PublicWebsocketChannel,
        visitor_id: str,
        request_id: str,
        client_message_id: str,
        text: str,
        source: str,
    ) -> InteractionAccepted:
        normalized_text = text.strip()
        if not normalized_text:
            raise AppError(
                "AI_INPUT_VALIDATION_ERROR",
                "Message text is required",
                status.HTTP_422_UNPROCESSABLE_CONTENT,
            )
        if len(normalized_text) > self.settings.limits.max_text_chars:
            raise AppError(
                "AI_INPUT_VALIDATION_ERROR",
                "Message text is too long",
                status.HTTP_422_UNPROCESSABLE_CONTENT,
            )
        scope = f"anonymous:{channel.tenant_id}:{channel.channel_id}:{visitor_id}:{source}"
        if not await self.redis.allow(
            scope,
            self.settings.anonymous.rate_limit_requests,
            self.settings.anonymous.rate_limit_window_seconds,
        ):
            raise AppError("RATE_LIMITED", "Too many requests", status.HTTP_429_TOO_MANY_REQUESTS)
        existing = await self.repository.inbound_by_message(
            channel.tenant_id, channel.channel_id, visitor_id, client_message_id
        )
        if existing is not None and existing.interaction_id is not None:
            return InteractionAccepted(
                interaction_id=existing.interaction_id,
                status="accepted",
            )
        service = InteractionService(
            self.session,
            self.database,
            self.runtime,
            self.redis,
            self.profile_resolver,
        )
        conversation_id = p2p_conversation_id(
            channel.tenant_id, channel.channel_id, channel.binding_id, "anonymous", visitor_id
        )
        accepted = await service.submit(
            AgentRuntimeTarget(
                id=channel.agent_id,
                tenant_id=channel.tenant_id,
                runtime_agent_id=channel.runtime_agent_id,
            ),
            InteractionSubmission(
                actor_type="anonymous",
                actor_id=visitor_id,
                entry_type="websocket",
                input_type="text",
                request_id=request_id,
                idempotency_key=client_message_id,
                text=normalized_text,
                conversation_id=conversation_id,
                im_channel_id=channel.channel_id,
                im_agent_binding_id=channel.binding_id,
                external_message_id=client_message_id,
                message_expires_at=utc_now()
                + timedelta(
                    days=getattr(self.settings.conversation_messages, "retention_days", 30)
                    if hasattr(self.settings, "conversation_messages")
                    else 30
                ),
            ),
        )
        # InteractionService commits its acceptance transaction. Tenant context is
        # transaction-local, so restore it before this IM-owned tenant write.
        await self.database.set_tenant(self.session, channel.tenant_id)
        await self.repository.record_inbound(
            ImInboundDelivery(
                id=new_id("im_inbound"),
                tenant_id=channel.tenant_id,
                channel_id=channel.channel_id,
                visitor_id=visitor_id,
                client_message_id=client_message_id,
                interaction_id=accepted.interaction_id,
                accepted=True,
            )
        )
        return accepted


def p2p_conversation_id(
    tenant_id: str,
    channel_id: str,
    binding_id: str,
    actor_type: str,
    actor_id: str,
) -> str:
    """Build an opaque, server-derived key scoped to one P2P binding participant."""
    value = "\x1f".join((tenant_id, channel_id, binding_id, actor_type, actor_id))
    return "p2p_" + hashlib.sha256(value.encode("utf-8")).hexdigest()
