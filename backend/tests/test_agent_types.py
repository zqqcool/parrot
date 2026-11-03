from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent_types import AgentTypeKey, agent_type_policy
from app.core.errors import AppError
from app.infrastructure.db.session import DatabaseManager
from app.modules.agents.models import AgentPublication, AgentType
from app.modules.agents.ports import AgentPublicationPolicy
from app.modules.agents.schemas import AgentCreateRequest, AgentUpdateRequest
from app.modules.agents.service import AgentService
from app.modules.iam.schemas import PrincipalContext


def principal(*permissions: str) -> PrincipalContext:
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


def test_agent_type_catalog_owns_the_default() -> None:
    payload = AgentCreateRequest(runtime_agent_id="runtime_test", slug="demo-agent", name="Demo")

    assert payload.agent_type_key is None
    assert AgentPublication.__table__.c.agent_type_key.default is None
    assert AgentPublication.__table__.c.agent_type_key.server_default is None


def test_agent_type_runtime_capabilities_are_centralized() -> None:
    functional = agent_type_policy(AgentTypeKey.FUNCTIONAL)
    knowledge = agent_type_policy(AgentTypeKey.KNOWLEDGE)
    voice = agent_type_policy(AgentTypeKey.VOICE)

    assert functional is not None
    assert functional.allows_runtime_tools is True
    assert functional.uses_functional_planner is True
    assert knowledge is not None
    assert knowledge.uses_knowledge is True
    assert knowledge.restricts_executable_skills is True
    assert voice is not None
    assert voice.allows_runtime_tools is False
    assert agent_type_policy("unsupported") is None


@pytest.mark.asyncio
async def test_list_agent_types_requires_read_permission() -> None:
    session = cast(AsyncSession, SimpleNamespace(scalars=AsyncMock()))
    service = AgentService(session, cast(DatabaseManager, SimpleNamespace()))

    with pytest.raises(AppError) as error:
        await service.list_types(principal())

    assert error.value.code == "FORBIDDEN"


@pytest.mark.asyncio
async def test_list_agent_types_returns_catalog_metadata() -> None:
    catalog = [
        AgentType(
            key="functional",
            name="功能型",
            description="面向复杂任务的自主推理，可使用本地沙盒执行环境。",
            is_default=True,
        )
    ]
    session = cast(AsyncSession, SimpleNamespace(scalars=AsyncMock(return_value=catalog)))
    service = AgentService(session, cast(DatabaseManager, SimpleNamespace()))

    result = await service.list_types(principal("agents.read"))

    assert result[0].key == "functional"
    assert result[0].description == catalog[0].description
    assert result[0].is_default is True
    assert result[0].uses_knowledge is False
    assert result[0].restricts_executable_skills is False


@pytest.mark.asyncio
async def test_create_rejects_unknown_agent_type() -> None:
    session_mock = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: None)),
        scalar=AsyncMock(return_value=None),
        add=Mock(),
        flush=AsyncMock(),
    )
    session = cast(AsyncSession, session_mock)
    service = AgentService(
        session,
        cast(DatabaseManager, SimpleNamespace(set_tenant=AsyncMock())),
    )
    payload = AgentCreateRequest(
        runtime_agent_id="runtime_test",
        slug="demo-agent",
        name="Demo",
        agent_type_key="unsupported",
    )

    with pytest.raises(AppError) as error:
        await service.create(principal("agents.manage"), "tenant_test", payload)

    assert error.value.code == "AGENT_TYPE_INVALID"
    session_mock.add.assert_not_called()


@pytest.mark.asyncio
async def test_create_uses_the_catalog_default_when_type_is_omitted() -> None:
    async def flush() -> None:
        session_mock.add.call_args.args[0].status = "active"

    session_mock = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: None)),
        scalar=AsyncMock(return_value="knowledge"),
        add=Mock(),
        flush=AsyncMock(side_effect=flush),
    )
    session = cast(AsyncSession, session_mock)
    service = AgentService(
        session,
        cast(DatabaseManager, SimpleNamespace(set_tenant=AsyncMock())),
    )
    payload = AgentCreateRequest(runtime_agent_id="runtime_test", slug="demo-agent", name="Demo")

    await service.create(principal("agents.manage"), "tenant_test", payload)

    assert session_mock.add.call_args_list[0].args[0].agent_type_key == "knowledge"


def test_public_agent_view_does_not_expose_system_prompt() -> None:
    agent = AgentPublication(
        id="agent_test",
        tenant_id="tenant_test",
        runtime_agent_id="runtime_test",
        slug="demo-agent",
        name="Demo",
        description="",
        system_prompt="private instructions",
        status="active",
        agent_type_key="knowledge",
        published=False,
        allow_anonymous=False,
    )

    assert "system_prompt" not in AgentService.view(agent).model_dump()
    assert "capability_relevance_threshold" not in AgentService.view(agent).model_dump()
    assert AgentService.admin_view(agent).system_prompt == "private instructions"
    assert AgentService.admin_view(agent).capability_relevance_threshold == 0.4


def test_agent_relevance_threshold_is_server_owned_and_bounded() -> None:
    assert AgentPublication.__table__.c.capability_relevance_threshold.server_default is not None
    assert (
        AgentUpdateRequest(capability_relevance_threshold=0.65).capability_relevance_threshold
        == 0.65
    )
    with pytest.raises(ValueError):
        AgentUpdateRequest(capability_relevance_threshold=-0.01)


@pytest.mark.asyncio
async def test_switching_to_knowledge_validates_existing_skill_bindings() -> None:
    agent = AgentPublication(
        id="agent_test",
        tenant_id="tenant_test",
        runtime_agent_id="runtime_test",
        slug="demo-agent",
        name="Demo",
        description="",
        system_prompt="",
        status="active",
        agent_type_key="functional",
        published=False,
        allow_anonymous=False,
    )
    policy = SimpleNamespace(
        ensure_agent_type_change_allowed=AsyncMock(),
        ensure_publishable=AsyncMock(),
    )
    session_mock = SimpleNamespace(
        add=Mock(),
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: agent)),
        refresh=AsyncMock(),
        scalar=AsyncMock(return_value=True),
    )
    service = AgentService(
        cast(AsyncSession, session_mock),
        cast(DatabaseManager, SimpleNamespace(set_tenant=AsyncMock())),
        cast(AgentPublicationPolicy, policy),
    )

    await service.update(
        principal("agents.manage"),
        "tenant_test",
        agent.id,
        AgentUpdateRequest(agent_type_key="knowledge"),
    )

    policy.ensure_agent_type_change_allowed.assert_awaited_once_with(
        "tenant_test", agent.id, "knowledge"
    )
