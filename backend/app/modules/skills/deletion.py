from __future__ import annotations

from typing import Protocol


class SkillDeletionGuard(Protocol):
    async def is_bound_to_agent(self, tenant_id: str, skill_id: str) -> bool: ...
