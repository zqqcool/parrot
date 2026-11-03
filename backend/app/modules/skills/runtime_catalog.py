from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent_runtime import RuntimeSkillProfile
from app.modules.skills.models import Skill


class SkillRuntimeCatalog:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_published(
        self, tenant_id: str, skill_ids: tuple[str, ...]
    ) -> tuple[RuntimeSkillProfile, ...]:
        if not skill_ids:
            return ()
        rows = await self.session.scalars(
            select(Skill).where(
                Skill.status == "published",
                Skill.tenant_id == tenant_id,
                Skill.id.in_(skill_ids),
            )
        )
        bound_skills: dict[str, RuntimeSkillProfile] = {}
        for item in rows:
            profile = RuntimeSkillProfile(
                id=item.id,
                name=item.name,
                description=item.description,
                instructions=item.instructions,
                manifest=item.manifest,
                version=item.version,
                package_path=item.runtime_artifact_path or item.package_path,
                package_sha256=item.runtime_artifact_sha256 or item.package_sha256,
            )
            bound_skills[item.id] = profile
        return tuple(bound_skills[skill_id] for skill_id in skill_ids if skill_id in bound_skills)
