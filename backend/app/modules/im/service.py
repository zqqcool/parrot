from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.errors import AppError
from app.core.ids import new_id
from app.infrastructure.db.session import DatabaseManager
from app.modules.agents.catalog import AgentCatalog
from app.modules.audit.service import append_audit
from app.modules.iam.permissions import PLATFORM_TENANTS_MANAGE
from app.modules.iam.schemas import PrincipalContext
from app.modules.im.channel_types import CHANNEL_TYPES, get_channel_type
from app.modules.im.models import ImAgentBinding, ImChannel
from app.modules.im.repository import ImChannelRepository
from app.modules.im.schemas import (
    ImAgentBindingRequest,
    ImAgentBindingView,
    ImChannelCreateRequest,
    ImChannelTypeView,
    ImChannelUpdateRequest,
    ImChannelView,
    PublicImChannelView,
)


@dataclass(frozen=True)
class PublicWebsocketChannel:
    channel_id: str
    binding_id: str
    tenant_id: str
    agent_id: str
    runtime_agent_id: str
    allowed_origins: tuple[str, ...]


class ImChannelService:
    def __init__(self, session: AsyncSession, database: DatabaseManager) -> None:
        self.session = session
        self.database = database
        self.repository = ImChannelRepository(session)
        self.agents = AgentCatalog(session)

    async def list_channels(
        self, principal: PrincipalContext, tenant_id: str
    ) -> list[ImChannelView]:
        await self._enter(principal, tenant_id, "im.channels.read")
        return [self._channel_view(item) for item in await self.repository.list_channels(tenant_id)]

    async def list_channel_types(
        self, principal: PrincipalContext, tenant_id: str
    ) -> list[ImChannelTypeView]:
        await self._enter(principal, tenant_id, "im.channels.read")
        return [
            ImChannelTypeView(
                key=item.key,
                label=item.label,
                enabled=item.enabled,
                description=item.description,
            )
            for item in CHANNEL_TYPES
        ]

    async def list_public_agent_channels(self, slug: str) -> list[PublicImChannelView]:
        target = await self.agents.get_anonymous_target_by_slug(slug)
        if target is None:
            raise AppError("RESOURCE_NOT_FOUND", "Agent not found", status.HTTP_404_NOT_FOUND)
        await self.database.set_tenant(self.session, target.tenant_id)
        bindings = await self.repository.list_agent_bindings(target.tenant_id, target.id)
        return [
            PublicImChannelView(
                channel_key=channel.public_key,
                channel_type=channel.channel_type,
                name=channel.name,
            )
            for binding, channel in bindings
            if binding.status == "enabled"
            and channel.status == "enabled"
            and channel.channel_type == "websocket"
        ]

    async def create_channel(
        self, principal: PrincipalContext, tenant_id: str, payload: ImChannelCreateRequest
    ) -> ImChannelView:
        await self._enter(principal, tenant_id, "im.channels.manage")
        channel_type = get_channel_type(payload.channel_type)
        if channel_type is None:
            raise AppError(
                "IM_CHANNEL_TYPE_UNKNOWN",
                "Channel type is unknown",
                status.HTTP_422_UNPROCESSABLE_CONTENT,
            )
        if not channel_type.enabled:
            raise AppError(
                "IM_CHANNEL_TYPE_UNAVAILABLE",
                "Channel adapter is not enabled",
                status.HTTP_409_CONFLICT,
            )
        item = ImChannel(
            id=new_id("im_channel"),
            tenant_id=tenant_id,
            channel_type=channel_type.key,
            name=payload.name.strip(),
            public_key=new_id("channel"),
            allowed_origins=list(payload.allowed_origins),
        )
        self.session.add(item)
        await self.session.flush()
        append_audit(
            self.session, principal, "im.channel.create", "im_channel", item.id, tenant_id=tenant_id
        )
        return self._channel_view(item)

    async def update_channel(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        channel_id: str,
        payload: ImChannelUpdateRequest,
    ) -> ImChannelView:
        await self._enter(principal, tenant_id, "im.channels.manage")
        item = await self._required_channel(tenant_id, channel_id)
        values = payload.model_dump(exclude_none=True)
        if "name" in values:
            item.name = str(values["name"]).strip()
        if "allowed_origins" in values:
            item.allowed_origins = list(values["allowed_origins"])
        if "status" in values:
            item.status = str(values["status"])
        await self.session.flush()
        append_audit(
            self.session, principal, "im.channel.update", "im_channel", item.id, tenant_id=tenant_id
        )
        return self._channel_view(item)

    async def bind_agent(
        self, principal: PrincipalContext, tenant_id: str, payload: ImAgentBindingRequest
    ) -> ImAgentBindingView:
        await self._enter(principal, tenant_id, "im.channels.manage")
        channel = await self._required_channel(tenant_id, payload.channel_id)
        if not await self.agents.exists(tenant_id, payload.agent_id):
            raise AppError("RESOURCE_NOT_FOUND", "Agent not found", status.HTTP_404_NOT_FOUND)
        existing = await self.repository.get_binding(tenant_id, channel.id)
        if existing is not None and existing.agent_id != payload.agent_id:
            raise AppError(
                "IM_CHANNEL_ALREADY_BOUND",
                "A WebSocket channel can bind only one Agent",
                status.HTTP_409_CONFLICT,
            )
        binding = existing or ImAgentBinding(
            id=new_id("im_binding"),
            tenant_id=tenant_id,
            channel_id=channel.id,
            agent_id=payload.agent_id,
        )
        if existing is None:
            self.session.add(binding)
        else:
            binding.status = "enabled"
        await self.session.flush()
        append_audit(
            self.session,
            principal,
            "im.agent_binding.upsert",
            "im_agent_binding",
            binding.id,
            {"channel_id": channel.id, "agent_id": binding.agent_id},
            tenant_id=tenant_id,
        )
        return self._binding_view(binding, channel)

    async def list_agent_bindings(
        self, principal: PrincipalContext, tenant_id: str, agent_id: str
    ) -> list[ImAgentBindingView]:
        await self._enter(principal, tenant_id, "im.channels.read")
        if not await self.agents.exists(tenant_id, agent_id):
            raise AppError("RESOURCE_NOT_FOUND", "Agent not found", status.HTTP_404_NOT_FOUND)
        return [
            self._binding_view(binding, channel)
            for binding, channel in await self.repository.list_agent_bindings(tenant_id, agent_id)
        ]

    async def resolve_websocket_channel(self, public_key: str) -> PublicWebsocketChannel:
        channel = await self.repository.get_public_channel(public_key)
        if channel is None or channel.status != "enabled" or channel.channel_type != "websocket":
            raise AppError("IM_CHANNEL_NOT_FOUND", "Channel not found", status.HTTP_404_NOT_FOUND)
        await self.database.set_tenant(self.session, channel.tenant_id)
        binding = await self.repository.get_binding(channel.tenant_id, channel.id)
        if binding is None or binding.status != "enabled":
            raise AppError(
                "IM_CHANNEL_NOT_BOUND", "Channel is not bound to an Agent", status.HTTP_409_CONFLICT
            )
        target = await self.agents.get_anonymous_target(channel.tenant_id, binding.agent_id)
        if target is None:
            raise AppError(
                "IM_CHANNEL_AGENT_UNAVAILABLE",
                "Bound Agent is unavailable",
                status.HTTP_409_CONFLICT,
            )
        return PublicWebsocketChannel(
            channel_id=channel.id,
            binding_id=binding.id,
            tenant_id=channel.tenant_id,
            agent_id=binding.agent_id,
            runtime_agent_id=target.runtime_agent_id,
            allowed_origins=tuple(channel.allowed_origins),
        )

    async def _required_channel(self, tenant_id: str, channel_id: str) -> ImChannel:
        item = await self.repository.get_channel(tenant_id, channel_id)
        if item is None:
            raise AppError("RESOURCE_NOT_FOUND", "IM channel not found", status.HTTP_404_NOT_FOUND)
        return item

    async def _enter(self, principal: PrincipalContext, tenant_id: str, permission: str) -> None:
        if (
            principal.tenant_id != tenant_id
            and PLATFORM_TENANTS_MANAGE not in principal.permissions
        ):
            raise AppError("RESOURCE_NOT_FOUND", "IM channel not found", status.HTTP_404_NOT_FOUND)
        if permission not in principal.permissions:
            raise AppError("FORBIDDEN", "Permission denied", status.HTTP_403_FORBIDDEN)
        await self.database.set_tenant(self.session, tenant_id)

    @staticmethod
    def _channel_view(item: ImChannel) -> ImChannelView:
        return ImChannelView(
            id=item.id,
            tenant_id=item.tenant_id,
            channel_type=item.channel_type,
            name=item.name,
            public_key=item.public_key,
            status=item.status,
            allowed_origins=tuple(item.allowed_origins),
            created_at=item.created_at,
            updated_at=item.updated_at,
        )

    @staticmethod
    def _binding_view(binding: ImAgentBinding, channel: ImChannel) -> ImAgentBindingView:
        return ImAgentBindingView(
            id=binding.id,
            tenant_id=binding.tenant_id,
            channel_id=binding.channel_id,
            agent_id=binding.agent_id,
            status=binding.status,
            channel_name=channel.name,
            channel_public_key=channel.public_key,
        )
