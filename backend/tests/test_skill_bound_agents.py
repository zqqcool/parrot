from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.session import DatabaseManager
from app.modules.agents.skill_usage import AgentSkillUsage
from app.modules.iam.schemas import PrincipalContext
from app.modules.skills.bound_agents import SkillBoundAgent
from app.modules.skills.models import Skill
from app.modules.skills.service import SkillService


@pytest.mark.asyncio
async def test_agent_skill_usage_groups_bound_agents_in_one_query() -> None:
    session = SimpleNamespace(
        execute=AsyncMock(
            return_value=SimpleNamespace(
                all=lambda: [
                    ("skill_weather", "agent_assistant", "Weather Assistant"),
                    ("skill_weather", "agent_ops", "Weather Operations"),
                    ("skill_search", "agent_search", "Search Assistant"),
                ]
            )
        )
    )

    result = await AgentSkillUsage(cast(AsyncSession, session)).list_bound_agents(
        "tenant_test", ("skill_weather", "skill_search")
    )

    assert result == {
        "skill_weather": (
            SkillBoundAgent("agent_assistant", "Weather Assistant"),
            SkillBoundAgent("agent_ops", "Weather Operations"),
        ),
        "skill_search": (SkillBoundAgent("agent_search", "Search Assistant"),),
    }
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_skill_list_hides_bound_agents_without_agent_read_permission() -> None:
    reader = _BoundAgentReader()
    skill = Skill(
        id="skill_weather",
        tenant_id="tenant_test",
        name="Weather",
        description="",
        status="published",
        version=1,
        manifest={},
        instructions="",
    )
    service = SkillService(
        cast(AsyncSession, SimpleNamespace(scalars=AsyncMock(return_value=[skill]))),
        cast(DatabaseManager, SimpleNamespace(set_tenant=AsyncMock())),
        bound_agent_reader=reader,
    )

    without_permission = await service.list(_principal("skills.read"), "tenant_test")
    with_permission = await service.list(_principal("skills.read", "agents.read"), "tenant_test")

    assert without_permission[0].bound_agents is None
    assert [agent.name for agent in with_permission[0].bound_agents or ()] == ["Weather"]
    assert reader.calls == [("tenant_test", ("skill_weather",))]


class _BoundAgentReader:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    async def list_bound_agents(
        self, tenant_id: str, skill_ids: tuple[str, ...]
    ) -> dict[str, tuple[SkillBoundAgent, ...]]:
        self.calls.append((tenant_id, skill_ids))
        return {"skill_weather": (SkillBoundAgent("agent_weather", "Weather"),)}


def _principal(*permissions: str) -> PrincipalContext:
    return PrincipalContext(
        tenant_id="tenant_test",
        subject_id="user_test",
        username="admin",
        display_name="Admin",
        permissions=permissions,
        tenants=(),
        must_change_password=False,
        request_id="req_test",
    )
