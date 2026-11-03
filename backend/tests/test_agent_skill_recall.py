from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.infrastructure.db.session import DatabaseManager
from app.modules.agents.schemas import AgentSkillRecallRequest
from app.modules.agents.skill_recall_service import AgentSkillRecallService
from app.modules.capability_index.hybrid_search import (
    CapabilitySearchEvaluator,
    CapabilitySearchOutcome,
)
from app.modules.iam.schemas import PrincipalContext
from app.modules.skills.models import Skill


@pytest.mark.asyncio
async def test_agent_skill_recall_reuses_runtime_scope_and_instruction_filter() -> None:
    instruction = _skill("skill_instruction", "Hotel Check-in", "Collect booking details.")
    executable = _skill(
        "skill_executable",
        "Booking API",
        "Create the booking.",
        manifest={"runtime": {"entrypoint": "main.py"}},
    )
    session = SimpleNamespace(
        scalar=AsyncMock(side_effect=("agent_test", "knowledge", 0.4)),
        scalars=AsyncMock(
            side_effect=(
                (instruction.id, executable.id),
                (instruction, executable),
            )
        ),
    )
    database = SimpleNamespace(set_tenant=AsyncMock())
    ranker = SimpleNamespace(
        evaluate=AsyncMock(
            return_value=CapabilitySearchOutcome(
                (instruction.id,),
                "hybrid",
                ((instruction.id, 0.72),),
            )
        )
    )
    service = AgentSkillRecallService(
        cast(AsyncSession, session),
        cast(DatabaseManager, database),
        cast(CapabilitySearchEvaluator, ranker),
    )

    result = await service.search(
        _principal("agents.read", "skills.read"),
        "tenant_test",
        "agent_test",
        AgentSkillRecallRequest(query="  酒店登记入住  ", relevance_threshold=0.55),
    )

    assert result.query == "酒店登记入住"
    assert result.retrieval_method == "hybrid"
    assert result.eligible_skill_count == 1
    assert result.configured_relevance_threshold == 0.4
    assert result.applied_relevance_threshold == 0.55
    assert [item.id for item in result.candidates] == [instruction.id]
    assert result.candidates[0].relevance_score == 0.72
    documents = ranker.evaluate.await_args.args[2]
    assert len(documents) == 1
    assert "name: Hotel Check-in" in documents[0].text
    assert "SKILL.md:\nCollect booking details." in documents[0].text
    assert ranker.evaluate.await_args.kwargs == {"minimum_relevance_score": 0.55}
    assert database.set_tenant.await_count == 2


def test_agent_skill_recall_threshold_must_be_a_probability() -> None:
    with pytest.raises(ValueError):
        AgentSkillRecallRequest(query="check in", relevance_threshold=1.01)


@pytest.mark.asyncio
async def test_agent_skill_recall_requires_skill_read_permission() -> None:
    session = SimpleNamespace(scalar=AsyncMock(), scalars=AsyncMock())
    database = SimpleNamespace(set_tenant=AsyncMock())
    ranker = SimpleNamespace(evaluate=AsyncMock())
    service = AgentSkillRecallService(
        cast(AsyncSession, session),
        cast(DatabaseManager, database),
        cast(CapabilitySearchEvaluator, ranker),
    )

    with pytest.raises(AppError) as captured:
        await service.search(
            _principal("agents.read"),
            "tenant_test",
            "agent_test",
            AgentSkillRecallRequest(query="check in"),
        )

    assert captured.value.code == "FORBIDDEN"
    session.scalar.assert_not_awaited()
    ranker.evaluate.assert_not_awaited()


def _skill(
    skill_id: str,
    name: str,
    instructions: str,
    *,
    manifest: dict[str, object] | None = None,
) -> Skill:
    return Skill(
        id=skill_id,
        tenant_id="tenant_test",
        name=name,
        description=f"{name} description",
        status="published",
        version=3,
        manifest=manifest or {},
        instructions=instructions,
    )


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
