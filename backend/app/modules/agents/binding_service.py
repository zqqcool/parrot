from __future__ import annotations

from starlette import status

from app.core.agent_types import agent_type_policy
from app.core.errors import AppError
from app.infrastructure.db.session import DatabaseManager
from app.modules.agents.ports import CapabilityCatalogPort, SkillCatalogPort
from app.modules.agents.repository import AgentBindingRepository
from app.modules.agents.schemas import (
    AgentLlmBindingsView,
    AgentMcpServerBindingsView,
    AgentSkillBindingsView,
)
from app.modules.audit.service import append_audit
from app.modules.iam.permissions import PLATFORM_TENANTS_MANAGE
from app.modules.iam.schemas import PrincipalContext


class AgentBindingService:
    def __init__(
        self,
        repository: AgentBindingRepository,
        database: DatabaseManager,
        llm_catalog: CapabilityCatalogPort,
        skill_catalog: SkillCatalogPort,
        mcp_catalog: CapabilityCatalogPort,
    ) -> None:
        self.repository = repository
        self.database = database
        self.llm_catalog = llm_catalog
        self.skill_catalog = skill_catalog
        self.mcp_catalog = mcp_catalog

    async def ensure_publishable(self, tenant_id: str, agent_id: str) -> None:
        ids, default_id = await self.repository.get_llm_bindings(tenant_id, agent_id)
        if default_id is None:
            raise AppError(
                "AGENT_LLM_REQUIRED",
                "Configure a default LLM before publishing the agent",
                status.HTTP_409_CONFLICT,
            )
        await self.llm_catalog.validate_ids(tenant_id, ids)
        skill_ids = await self.repository.get_skill_bindings(tenant_id, agent_id)
        agent_type_key = await self.repository.get_agent_type_key(tenant_id, agent_id)
        await self._validate_skills_for_type(tenant_id, skill_ids, agent_type_key)
        mcp_server_ids = await self.repository.get_mcp_server_bindings(tenant_id, agent_id)
        await self.mcp_catalog.validate_ids(tenant_id, mcp_server_ids)

    async def get_llm_bindings(
        self, principal: PrincipalContext, tenant_id: str, agent_id: str
    ) -> AgentLlmBindingsView:
        await self._enter(principal, tenant_id, "agents.read", agent_id)
        ids, default_id = await self.repository.get_llm_bindings(tenant_id, agent_id)
        return AgentLlmBindingsView(ids=ids, default_id=default_id)

    async def replace_llm_bindings(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        agent_id: str,
        ids: tuple[str, ...],
        default_id: str,
    ) -> AgentLlmBindingsView:
        await self._enter(principal, tenant_id, "agents.manage", agent_id)
        unique_ids = tuple(dict.fromkeys(ids))
        if len(unique_ids) != 1:
            raise AppError(
                "AGENT_SINGLE_LLM_REQUIRED",
                "An Agent must have exactly one LLM configuration",
                status.HTTP_422_UNPROCESSABLE_CONTENT,
            )
        if default_id not in unique_ids:
            raise AppError(
                "DEFAULT_LLM_NOT_BOUND",
                "Default LLM configuration must be included in ids",
                status.HTTP_422_UNPROCESSABLE_CONTENT,
            )
        await self.llm_catalog.validate_ids(tenant_id, unique_ids)
        await self.repository.replace_llm_bindings(tenant_id, agent_id, unique_ids, default_id)
        append_audit(
            self.repository.session,
            principal,
            "agent.llm_bindings.replace",
            "agent",
            agent_id,
            {"ids": unique_ids, "default_id": default_id},
            tenant_id=tenant_id,
        )
        return AgentLlmBindingsView(ids=unique_ids, default_id=default_id)

    async def get_skill_bindings(
        self, principal: PrincipalContext, tenant_id: str, agent_id: str
    ) -> AgentSkillBindingsView:
        await self._enter(principal, tenant_id, "agents.read", agent_id)
        ids = await self.repository.get_skill_bindings(tenant_id, agent_id)
        return AgentSkillBindingsView(ids=ids)

    async def replace_skill_bindings(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        agent_id: str,
        ids: tuple[str, ...],
    ) -> AgentSkillBindingsView:
        await self._enter(principal, tenant_id, "agents.manage", agent_id)
        unique_ids = tuple(dict.fromkeys(ids))
        agent_type_key = await self.repository.get_agent_type_key(tenant_id, agent_id)
        await self._validate_skills_for_type(tenant_id, unique_ids, agent_type_key)
        await self.repository.replace_skill_bindings(tenant_id, agent_id, unique_ids)
        append_audit(
            self.repository.session,
            principal,
            "agent.skill_bindings.replace",
            "agent",
            agent_id,
            {"ids": unique_ids},
            tenant_id=tenant_id,
        )
        return AgentSkillBindingsView(ids=unique_ids)

    async def ensure_agent_type_change_allowed(
        self, tenant_id: str, agent_id: str, agent_type_key: str
    ) -> None:
        policy = agent_type_policy(agent_type_key)
        if policy is None or not policy.restricts_executable_skills:
            return
        skill_ids = await self.repository.get_skill_bindings(tenant_id, agent_id)
        await self.skill_catalog.validate_instruction_only_ids(tenant_id, skill_ids)

    async def get_mcp_server_bindings(
        self, principal: PrincipalContext, tenant_id: str, agent_id: str
    ) -> AgentMcpServerBindingsView:
        await self._enter(principal, tenant_id, "agents.read", agent_id)
        ids = await self.repository.get_mcp_server_bindings(tenant_id, agent_id)
        return AgentMcpServerBindingsView(ids=ids)

    async def replace_mcp_server_bindings(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        agent_id: str,
        ids: tuple[str, ...],
    ) -> AgentMcpServerBindingsView:
        await self._enter(principal, tenant_id, "agents.manage", agent_id)
        unique_ids = tuple(dict.fromkeys(ids))
        await self.mcp_catalog.validate_ids(tenant_id, unique_ids)
        await self.repository.replace_mcp_server_bindings(tenant_id, agent_id, unique_ids)
        append_audit(
            self.repository.session,
            principal,
            "agent.mcp_server_bindings.replace",
            "agent",
            agent_id,
            {"ids": unique_ids},
            tenant_id=tenant_id,
        )
        return AgentMcpServerBindingsView(ids=unique_ids)

    async def _enter(
        self, principal: PrincipalContext, tenant_id: str, permission: str, agent_id: str
    ) -> None:
        if (
            principal.tenant_id != tenant_id
            and PLATFORM_TENANTS_MANAGE not in principal.permissions
        ):
            raise AppError("RESOURCE_NOT_FOUND", "Agent not found", status.HTTP_404_NOT_FOUND)
        if permission not in principal.permissions:
            raise AppError("FORBIDDEN", "Permission denied", status.HTTP_403_FORBIDDEN)
        await self.database.set_tenant(self.repository.session, tenant_id)
        if not await self.repository.agent_exists(tenant_id, agent_id):
            raise AppError("RESOURCE_NOT_FOUND", "Agent not found", status.HTTP_404_NOT_FOUND)

    async def _validate_skills_for_type(
        self, tenant_id: str, skill_ids: tuple[str, ...], agent_type_key: str | None
    ) -> None:
        policy = agent_type_policy(agent_type_key) if agent_type_key is not None else None
        if policy is not None and policy.restricts_executable_skills:
            await self.skill_catalog.validate_instruction_only_ids(tenant_id, skill_ids)
            return
        await self.skill_catalog.validate_ids(tenant_id, skill_ids)
