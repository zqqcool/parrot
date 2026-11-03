from __future__ import annotations

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.agents.models import (
    AgentLlmConfigBinding,
    AgentMcpServerBinding,
    AgentPublication,
    AgentSkillBinding,
    AgentType,
)


class AgentTypeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def exists(self, key: str) -> bool:
        value = await self.session.scalar(select(AgentType.key).where(AgentType.key == key))
        return value is not None

    async def list_all(self) -> list[AgentType]:
        rows = await self.session.scalars(
            select(AgentType).order_by(AgentType.is_default.desc(), AgentType.key)
        )
        return list(rows)

    async def default_key(self) -> str | None:
        return await self.session.scalar(
            select(AgentType.key).where(AgentType.is_default.is_(True))
        )


class AgentPublicationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_public(
        self, *, offset: int, limit: int, search: str | None
    ) -> list[AgentPublication]:
        statement = select(AgentPublication).where(
            AgentPublication.status == "active",
            AgentPublication.published.is_(True),
            AgentPublication.allow_anonymous.is_(True),
        )
        normalized_search = search.strip() if search else ""
        if normalized_search:
            statement = statement.where(
                or_(
                    AgentPublication.name.icontains(normalized_search, autoescape=True),
                    AgentPublication.description.icontains(normalized_search, autoescape=True),
                )
            )
        rows = await self.session.scalars(
            statement.order_by(AgentPublication.name, AgentPublication.id)
            .offset(offset)
            .limit(limit)
        )
        return list(rows)


class AgentBindingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def agent_exists(self, tenant_id: str, agent_id: str) -> bool:
        value = await self.session.scalar(
            select(AgentPublication.id).where(
                AgentPublication.tenant_id == tenant_id,
                AgentPublication.id == agent_id,
            )
        )
        return value is not None

    async def get_system_prompt(self, tenant_id: str, agent_id: str) -> str | None:
        return await self.session.scalar(
            select(AgentPublication.system_prompt).where(
                AgentPublication.tenant_id == tenant_id,
                AgentPublication.id == agent_id,
            )
        )

    async def get_agent_type_key(self, tenant_id: str, agent_id: str) -> str | None:
        return await self.session.scalar(
            select(AgentPublication.agent_type_key).where(
                AgentPublication.tenant_id == tenant_id,
                AgentPublication.id == agent_id,
            )
        )

    async def get_capability_relevance_threshold(
        self, tenant_id: str, agent_id: str
    ) -> float | None:
        return await self.session.scalar(
            select(AgentPublication.capability_relevance_threshold).where(
                AgentPublication.tenant_id == tenant_id,
                AgentPublication.id == agent_id,
            )
        )

    async def get_llm_bindings(
        self, tenant_id: str, agent_id: str
    ) -> tuple[tuple[str, ...], str | None]:
        rows = await self.session.scalars(
            select(AgentLlmConfigBinding).where(
                AgentLlmConfigBinding.tenant_id == tenant_id,
                AgentLlmConfigBinding.agent_id == agent_id,
            )
        )
        items = tuple(rows)
        default_id = next((item.llm_config_id for item in items if item.is_default), None)
        return tuple(item.llm_config_id for item in items), default_id

    async def replace_llm_bindings(
        self, tenant_id: str, agent_id: str, ids: tuple[str, ...], default_id: str
    ) -> None:
        await self.session.execute(
            delete(AgentLlmConfigBinding).where(
                AgentLlmConfigBinding.tenant_id == tenant_id,
                AgentLlmConfigBinding.agent_id == agent_id,
            )
        )
        self.session.add_all(
            AgentLlmConfigBinding(
                tenant_id=tenant_id,
                agent_id=agent_id,
                llm_config_id=config_id,
                is_default=config_id == default_id,
            )
            for config_id in ids
        )

    async def get_skill_bindings(self, tenant_id: str, agent_id: str) -> tuple[str, ...]:
        rows = await self.session.scalars(
            select(AgentSkillBinding.skill_id).where(
                AgentSkillBinding.tenant_id == tenant_id,
                AgentSkillBinding.agent_id == agent_id,
            )
        )
        return tuple(rows)

    async def replace_skill_bindings(
        self, tenant_id: str, agent_id: str, ids: tuple[str, ...]
    ) -> None:
        await self.session.execute(
            delete(AgentSkillBinding).where(
                AgentSkillBinding.tenant_id == tenant_id,
                AgentSkillBinding.agent_id == agent_id,
            )
        )
        self.session.add_all(
            AgentSkillBinding(tenant_id=tenant_id, agent_id=agent_id, skill_id=skill_id)
            for skill_id in ids
        )

    async def get_mcp_server_bindings(self, tenant_id: str, agent_id: str) -> tuple[str, ...]:
        rows = await self.session.scalars(
            select(AgentMcpServerBinding.mcp_server_id).where(
                AgentMcpServerBinding.tenant_id == tenant_id,
                AgentMcpServerBinding.agent_id == agent_id,
            )
        )
        return tuple(rows)

    async def replace_mcp_server_bindings(
        self, tenant_id: str, agent_id: str, ids: tuple[str, ...]
    ) -> None:
        await self.session.execute(
            delete(AgentMcpServerBinding).where(
                AgentMcpServerBinding.tenant_id == tenant_id,
                AgentMcpServerBinding.agent_id == agent_id,
            )
        )
        self.session.add_all(
            AgentMcpServerBinding(tenant_id=tenant_id, agent_id=agent_id, mcp_server_id=server_id)
            for server_id in ids
        )
