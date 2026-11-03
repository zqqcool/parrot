from __future__ import annotations

from starlette import status

from app.core.agent_runtime import (
    DEFAULT_CAPABILITY_RELEVANCE_THRESHOLD,
    AgentRuntimeProfile,
)
from app.core.agent_types import AgentTypeKey, agent_type_policy
from app.core.errors import AppError
from app.modules.agents.repository import AgentBindingRepository
from app.modules.llm_configs.runtime_catalog import LlmRuntimeCatalog
from app.modules.mcp_servers.runtime_catalog import McpRuntimeCatalog
from app.modules.skills.runtime_catalog import SkillRuntimeCatalog


class BoundAgentRuntimeProfileResolver:
    """Resolves only tenant-scoped capabilities explicitly bound to an agent."""

    def __init__(
        self,
        bindings: AgentBindingRepository,
        llm_catalog: LlmRuntimeCatalog,
        skill_catalog: SkillRuntimeCatalog,
        mcp_catalog: McpRuntimeCatalog,
    ) -> None:
        self.bindings = bindings
        self.llm_catalog = llm_catalog
        self.skill_catalog = skill_catalog
        self.mcp_catalog = mcp_catalog

    async def resolve(self, tenant_id: str, agent_id: str) -> AgentRuntimeProfile:
        system_prompt = await self.bindings.get_system_prompt(tenant_id, agent_id)
        type_resolver = getattr(self.bindings, "get_agent_type_key", None)
        agent_type_key = (
            AgentTypeKey.FUNCTIONAL
            if type_resolver is None
            else await type_resolver(tenant_id, agent_id)
        )
        policy = agent_type_policy(agent_type_key) if agent_type_key is not None else None
        threshold_resolver = getattr(self.bindings, "get_capability_relevance_threshold", None)
        relevance_threshold = (
            DEFAULT_CAPABILITY_RELEVANCE_THRESHOLD
            if threshold_resolver is None
            else await threshold_resolver(tenant_id, agent_id)
        )
        if (
            system_prompt is None
            or agent_type_key is None
            or policy is None
            or relevance_threshold is None
            or not 0 <= relevance_threshold <= 1
        ):
            raise self._invalid_configuration()
        config_ids, default_id = await self.bindings.get_llm_bindings(tenant_id, agent_id)
        if default_id is None or default_id not in config_ids:
            raise self._invalid_configuration()
        llm = await self.llm_catalog.get_active(tenant_id, default_id)
        if llm is None:
            raise self._invalid_configuration()
        skill_ids = await self.bindings.get_skill_bindings(tenant_id, agent_id)
        skills = await self.skill_catalog.get_published(tenant_id, skill_ids)
        if len(skills) != len(skill_ids):
            raise self._invalid_configuration()
        mcp_server_ids = await self.bindings.get_mcp_server_bindings(tenant_id, agent_id)
        mcp_servers = await self.mcp_catalog.get_active(tenant_id, mcp_server_ids)
        if len(mcp_servers) != len(mcp_server_ids):
            raise self._invalid_configuration()
        if policy.restricts_executable_skills:
            skills = tuple(skill for skill in skills if skill.is_instruction_only)
            mcp_servers = tuple(server for server in mcp_servers if not server.is_local_process)
        elif not policy.allows_runtime_tools:
            skills = ()
            mcp_servers = ()
        return AgentRuntimeProfile(
            llm=llm,
            skills=skills,
            system_prompt=system_prompt,
            mcp_servers=mcp_servers,
            agent_type_key=agent_type_key,
            capability_relevance_threshold=relevance_threshold,
        )

    @staticmethod
    def _invalid_configuration() -> AppError:
        return AppError(
            "AI_RUNTIME_CONFIGURATION_INVALID",
            "Agent runtime configuration is incomplete or unavailable",
            status.HTTP_409_CONFLICT,
        )
