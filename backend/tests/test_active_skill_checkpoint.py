from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest

from app.infrastructure.db.session import DatabaseManager
from app.modules.agent_runtime.active_skill import (
    SqlActiveSkillCheckpointStore,
    SqlSkillContextCheckpointStore,
)
from app.modules.interactions.models import Interaction
from app.modules.interactions.runtime import RuntimeActiveSkill, RuntimeSkillContext


class _Database:
    def __init__(self, interaction: Interaction) -> None:
        self._session = SimpleNamespace(
            scalar=AsyncMock(return_value=interaction),
            flush=AsyncMock(),
        )
        self.set_tenant = AsyncMock()

    @property
    def session_value(self) -> SimpleNamespace:
        return self._session

    @asynccontextmanager
    async def session(self):
        yield self._session


def _interaction() -> Interaction:
    return Interaction(
        id="interaction_test",
        tenant_id="tenant_test",
        agent_id="agent_test",
        actor_type="anonymous",
        actor_id="visitor_test",
        entry_type="websocket",
        input_type="text",
        status="running",
        input_payload={},
    )


@pytest.mark.asyncio
async def test_skill_context_checkpoint_pins_primary_and_supporting_skills() -> None:
    interaction = _interaction()
    database = _Database(interaction)
    store = SqlSkillContextCheckpointStore(cast(DatabaseManager, database))

    primary = await store.pin(
        tenant_id="tenant_test",
        interaction_id="interaction_test",
        role="primary",
        skill_id="skill_hotel",
        skill_version=3,
    )
    context = await store.pin(
        tenant_id="tenant_test",
        interaction_id="interaction_test",
        role="supporting",
        skill_id="skill_weather",
        skill_version=2,
    )

    assert primary == RuntimeSkillContext(primary=RuntimeActiveSkill("skill_hotel", 3))
    assert context == RuntimeSkillContext(
        primary=RuntimeActiveSkill("skill_hotel", 3),
        supporting=(RuntimeActiveSkill("skill_weather", 2),),
    )
    assert interaction.input_payload == {
        "skill_context": {
            "schema_version": 1,
            "primary": {"skill_id": "skill_hotel", "skill_version": 3},
            "supporting": [
                {"skill_id": "skill_weather", "skill_version": 2},
            ],
        }
    }


@pytest.mark.asyncio
async def test_active_skill_checkpoint_adapter_rejects_switching_primary_skill() -> None:
    interaction = _interaction()
    database = _Database(interaction)
    store = SqlActiveSkillCheckpointStore(cast(DatabaseManager, database))

    activated = await store.activate(
        tenant_id="tenant_test",
        interaction_id="interaction_test",
        skill_id="skill_hotel",
        skill_version=3,
    )
    repeated = await store.activate(
        tenant_id="tenant_test",
        interaction_id="interaction_test",
        skill_id="skill_hotel",
        skill_version=3,
    )
    switched = await store.activate(
        tenant_id="tenant_test",
        interaction_id="interaction_test",
        skill_id="skill_other",
        skill_version=1,
    )

    assert activated is True
    assert repeated is True
    assert switched is False
    assert interaction.input_payload["skill_context"] == {
        "schema_version": 1,
        "primary": {"skill_id": "skill_hotel", "skill_version": 3},
        "supporting": [],
    }
    database.set_tenant.assert_awaited_with(database.session_value, "tenant_test")


@pytest.mark.asyncio
async def test_supporting_skill_pin_migrates_a_legacy_active_skill_checkpoint() -> None:
    interaction = _interaction()
    interaction.input_payload = {
        "text": "continue",
        "active_skill": {"skill_id": "skill_primary", "skill_version": 4},
    }
    database = _Database(interaction)
    store = SqlSkillContextCheckpointStore(cast(DatabaseManager, database))

    context = await store.pin(
        tenant_id="tenant_test",
        interaction_id="interaction_test",
        role="supporting",
        skill_id="skill_supporting",
        skill_version=2,
    )

    assert context == RuntimeSkillContext(
        primary=RuntimeActiveSkill("skill_primary", 4),
        supporting=(RuntimeActiveSkill("skill_supporting", 2),),
    )
    assert "active_skill" not in interaction.input_payload
    assert interaction.input_payload["text"] == "continue"
    assert interaction.input_payload["skill_context"] == {
        "schema_version": 1,
        "primary": {"skill_id": "skill_primary", "skill_version": 4},
        "supporting": [
            {"skill_id": "skill_supporting", "skill_version": 2},
        ],
    }
