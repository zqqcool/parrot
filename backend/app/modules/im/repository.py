from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.im.models import ImAgentBinding, ImChannel, ImInboundDelivery


class ImChannelRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_channels(self, tenant_id: str) -> tuple[ImChannel, ...]:
        rows = await self.session.scalars(
            select(ImChannel).where(ImChannel.tenant_id == tenant_id).order_by(ImChannel.name)
        )
        return tuple(rows)

    async def get_channel(self, tenant_id: str, channel_id: str) -> ImChannel | None:
        return await self.session.scalar(
            select(ImChannel).where(ImChannel.tenant_id == tenant_id, ImChannel.id == channel_id)
        )

    async def get_public_channel(self, public_key: str) -> ImChannel | None:
        return await self.session.scalar(
            select(ImChannel).where(ImChannel.public_key == public_key)
        )

    async def get_binding(self, tenant_id: str, channel_id: str) -> ImAgentBinding | None:
        return await self.session.scalar(
            select(ImAgentBinding).where(
                ImAgentBinding.tenant_id == tenant_id,
                ImAgentBinding.channel_id == channel_id,
            )
        )

    async def list_agent_bindings(
        self, tenant_id: str, agent_id: str
    ) -> tuple[tuple[ImAgentBinding, ImChannel], ...]:
        rows = await self.session.execute(
            select(ImAgentBinding, ImChannel)
            .join(ImChannel, ImChannel.id == ImAgentBinding.channel_id)
            .where(ImAgentBinding.tenant_id == tenant_id, ImAgentBinding.agent_id == agent_id)
            .order_by(ImChannel.name)
        )
        return tuple(rows.tuples())

    async def inbound_by_message(
        self, tenant_id: str, channel_id: str, visitor_id: str, message_id: str
    ) -> ImInboundDelivery | None:
        return await self.session.scalar(
            select(ImInboundDelivery).where(
                ImInboundDelivery.tenant_id == tenant_id,
                ImInboundDelivery.channel_id == channel_id,
                ImInboundDelivery.visitor_id == visitor_id,
                ImInboundDelivery.client_message_id == message_id,
            )
        )

    async def record_inbound(self, delivery: ImInboundDelivery) -> None:
        statement = (
            insert(ImInboundDelivery)
            .values(
                id=delivery.id,
                tenant_id=delivery.tenant_id,
                channel_id=delivery.channel_id,
                visitor_id=delivery.visitor_id,
                client_message_id=delivery.client_message_id,
                interaction_id=delivery.interaction_id,
                accepted=delivery.accepted,
            )
            .on_conflict_do_nothing(constraint="uq_im_inbound_channel_visitor_message")
        )
        await self.session.execute(statement)
