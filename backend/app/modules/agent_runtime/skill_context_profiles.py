from __future__ import annotations

from app.core.agent_runtime import RuntimeSkillProfile
from app.modules.interactions.runtime import RuntimeActiveSkill, RuntimeSkillContext


def current_skill_context(
    context: RuntimeSkillContext | None,
    primary: RuntimeActiveSkill | None,
) -> RuntimeSkillContext:
    return context or RuntimeSkillContext(primary=primary)


def primary_skill_profile(
    skills: tuple[RuntimeSkillProfile, ...],
    primary: RuntimeActiveSkill | None,
) -> RuntimeSkillProfile | None:
    if primary is None:
        return None
    return next(
        (
            item
            for item in skills
            if item.id == primary.skill_id and item.version == primary.skill_version
        ),
        None,
    )


def supporting_skill_profiles(
    skills: tuple[RuntimeSkillProfile, ...],
    context: RuntimeSkillContext,
) -> tuple[RuntimeSkillProfile, ...]:
    by_identity = {(item.id, item.version): item for item in skills}
    return tuple(
        profile
        for pinned in context.supporting
        if (profile := by_identity.get((pinned.skill_id, pinned.skill_version))) is not None
    )


def pinned_skill(context: RuntimeSkillContext, skill_id: str) -> RuntimeActiveSkill | None:
    if context.primary is not None and context.primary.skill_id == skill_id:
        return context.primary
    return next((item for item in context.supporting if item.skill_id == skill_id), None)


def unavailable_pinned_skill(
    skills: tuple[RuntimeSkillProfile, ...],
    context: RuntimeSkillContext,
) -> RuntimeActiveSkill | None:
    identities = {(item.id, item.version) for item in skills}
    pinned = ((context.primary,) if context.primary is not None else ()) + context.supporting
    return next(
        (item for item in pinned if (item.skill_id, item.skill_version) not in identities),
        None,
    )
