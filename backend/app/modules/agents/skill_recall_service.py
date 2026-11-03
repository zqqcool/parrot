from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.agent_types import agent_type_policy
from app.core.errors import AppError
from app.infrastructure.db.session import DatabaseManager
from app.modules.agents.repository import AgentBindingRepository
from app.modules.agents.schemas import (
    AgentSkillRecallCandidateView,
    AgentSkillRecallRequest,
    AgentSkillRecallView,
)
from app.modules.capabilities.authorization import enter_tenant_capability_scope
from app.modules.capability_index.documents import skill_index_text
from app.modules.capability_index.hybrid_search import CapabilitySearchEvaluator
from app.modules.capability_index.ranking import CapabilitySearchDocument
from app.modules.iam.permissions import AGENTS_READ, SKILLS_READ
from app.modules.iam.schemas import PrincipalContext
from app.modules.skills.runtime_catalog import SkillRuntimeCatalog


class AgentSkillRecallService:
    """Runs the same bound-Skill ranking used by capability_search without loading a Skill."""

    def __init__(
        self,
        session: AsyncSession,
        database: DatabaseManager,
        search: CapabilitySearchEvaluator,
    ) -> None:
        self._session = session
        self._database = database
        self._search = search
        self._bindings = AgentBindingRepository(session)
        self._skills = SkillRuntimeCatalog(session)

    async def search(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        agent_id: str,
        payload: AgentSkillRecallRequest,
    ) -> AgentSkillRecallView:
        await self._enter(principal, tenant_id)
        if not await self._bindings.agent_exists(tenant_id, agent_id):
            raise AppError("RESOURCE_NOT_FOUND", "Agent not found", status.HTTP_404_NOT_FOUND)
        agent_type_key = await self._bindings.get_agent_type_key(tenant_id, agent_id)
        policy = agent_type_policy(agent_type_key) if agent_type_key is not None else None
        if agent_type_key is None or policy is None:
            raise self._invalid_runtime()
        configured_threshold = await self._bindings.get_capability_relevance_threshold(
            tenant_id, agent_id
        )
        if configured_threshold is None or not 0 <= configured_threshold <= 1:
            raise self._invalid_runtime()
        applied_threshold = payload.relevance_threshold
        if applied_threshold is None:
            applied_threshold = configured_threshold
        skill_ids = await self._bindings.get_skill_bindings(tenant_id, agent_id)
        skills = await self._skills.get_published(tenant_id, skill_ids)
        if len(skills) != len(skill_ids):
            raise self._invalid_runtime()
        if policy.restricts_executable_skills:
            skills = tuple(skill for skill in skills if skill.is_instruction_only)
        elif not policy.allows_runtime_tools:
            skills = ()
        documents = tuple(
            CapabilitySearchDocument(
                skill.id,
                skill_index_text(skill.name, skill.description, skill.instructions),
            )
            for skill in skills
        )
        outcome = await self._search.evaluate(
            tenant_id,
            payload.query,
            documents,
            minimum_relevance_score=applied_threshold,
        )
        by_id = {skill.id: skill for skill in skills}
        candidates = tuple(
            AgentSkillRecallCandidateView(
                id=skill.id,
                name=skill.name,
                description=skill.description,
                version=skill.version,
                rank=rank,
                relevance_score=outcome.relevance_score_for(skill.id),
            )
            for rank, skill_id in enumerate(outcome.source_ids[:2], start=1)
            if (skill := by_id.get(skill_id)) is not None
        )
        return AgentSkillRecallView(
            agent_id=agent_id,
            agent_type_key=agent_type_key,
            query=payload.query,
            retrieval_method=outcome.retrieval_method,
            eligible_skill_count=len(skills),
            configured_relevance_threshold=configured_threshold,
            applied_relevance_threshold=applied_threshold,
            candidates=candidates,
        )

    async def _enter(self, principal: PrincipalContext, tenant_id: str) -> None:
        await enter_tenant_capability_scope(
            self._database, self._session, principal, tenant_id, AGENTS_READ, "Agent"
        )
        await enter_tenant_capability_scope(
            self._database, self._session, principal, tenant_id, SKILLS_READ, "Skill"
        )

    @staticmethod
    def _invalid_runtime() -> AppError:
        return AppError(
            "AI_RUNTIME_CONFIGURATION_INVALID",
            "Agent runtime configuration is incomplete or unavailable",
            status.HTTP_409_CONFLICT,
        )
