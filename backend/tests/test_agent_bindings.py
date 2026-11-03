from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.infrastructure.db.session import DatabaseManager
from app.modules.agents.binding_service import AgentBindingService
from app.modules.agents.ports import CapabilityCatalogPort, SkillCatalogPort
from app.modules.agents.repository import AgentBindingRepository
from app.modules.agents.schemas import AgentUpdateRequest
from app.modules.agents.service import AgentService, audit_values_for_agent_update
from app.modules.audit.service import append_audit
from app.modules.iam.schemas import PrincipalContext


def principal(*permissions: str, tenant_id: str = "tenant_test") -> PrincipalContext:
    return PrincipalContext(
        tenant_id=tenant_id,
        subject_id="user_test",
        username="admin",
        display_name="Admin",
        permissions=permissions,
        tenants=(),
        must_change_password=False,
        request_id="req_test",
    )


def service() -> tuple[
    AgentBindingService, SimpleNamespace, SimpleNamespace, SimpleNamespace, SimpleNamespace
]:
    session = SimpleNamespace(add=Mock())
    repository = SimpleNamespace(
        session=session,
        agent_exists=AsyncMock(return_value=True),
        get_agent_type_key=AsyncMock(return_value="functional"),
        get_llm_bindings=AsyncMock(return_value=(("llm_one",), "llm_one")),
        replace_llm_bindings=AsyncMock(),
        get_skill_bindings=AsyncMock(return_value=("skill_one",)),
        replace_skill_bindings=AsyncMock(),
        get_mcp_server_bindings=AsyncMock(return_value=("mcp_one",)),
        replace_mcp_server_bindings=AsyncMock(),
    )
    llm_catalog = SimpleNamespace(validate_ids=AsyncMock())
    skill_catalog = SimpleNamespace(
        validate_ids=AsyncMock(),
        validate_instruction_only_ids=AsyncMock(),
    )
    mcp_catalog = SimpleNamespace(validate_ids=AsyncMock())
    database = SimpleNamespace(set_tenant=AsyncMock())
    binding_service = AgentBindingService(
        cast(AgentBindingRepository, repository),
        cast(DatabaseManager, database),
        cast(CapabilityCatalogPort, llm_catalog),
        cast(SkillCatalogPort, skill_catalog),
        cast(CapabilityCatalogPort, mcp_catalog),
    )
    return binding_service, repository, llm_catalog, skill_catalog, mcp_catalog


def test_audit_metadata_is_json_safe_before_commit() -> None:
    session = SimpleNamespace(add=Mock())
    published_at = datetime(2026, 7, 13, 12, 30, tzinfo=UTC)

    append_audit(
        cast(AsyncSession, session),
        principal("agents.publish"),
        "agent.update",
        "agent",
        "agent_test",
        {"published": True, "published_at": published_at, "ids": ("llm_one",)},
    )

    audit = session.add.call_args.args[0]
    assert audit.metadata_json == {
        "published": True,
        "published_at": "2026-07-13T12:30:00+00:00",
        "ids": ["llm_one"],
    }


def test_agent_system_prompt_is_redacted_from_audit_metadata() -> None:
    assert audit_values_for_agent_update(
        {"name": "Assistant", "system_prompt": "Private instruction"}
    ) == {
        "name": "Assistant",
        "system_prompt_configured": True,
    }


@pytest.mark.asyncio
async def test_replace_bindings_validates_catalog_and_deduplicates() -> None:
    binding_service, repository, llm_catalog, skill_catalog, mcp_catalog = service()

    llm_result = await binding_service.replace_llm_bindings(
        principal("agents.manage"),
        "tenant_test",
        "agent_test",
        ("llm_one", "llm_one"),
        "llm_one",
    )
    skill_result = await binding_service.replace_skill_bindings(
        principal("agents.manage"),
        "tenant_test",
        "agent_test",
        ("skill_one", "skill_one"),
    )
    mcp_result = await binding_service.replace_mcp_server_bindings(
        principal("agents.manage"),
        "tenant_test",
        "agent_test",
        ("mcp_one", "mcp_one"),
    )

    assert llm_result.ids == ("llm_one",)
    assert skill_result.ids == ("skill_one",)
    assert mcp_result.ids == ("mcp_one",)
    llm_catalog.validate_ids.assert_awaited_once_with("tenant_test", ("llm_one",))
    skill_catalog.validate_ids.assert_awaited_once_with("tenant_test", ("skill_one",))
    mcp_catalog.validate_ids.assert_awaited_once_with("tenant_test", ("mcp_one",))
    repository.replace_llm_bindings.assert_awaited_once()
    repository.replace_skill_bindings.assert_awaited_once()
    repository.replace_mcp_server_bindings.assert_awaited_once()


@pytest.mark.asyncio
async def test_knowledge_agent_only_validates_instruction_only_skill_bindings() -> None:
    binding_service, repository, _, skill_catalog, _ = service()
    repository.get_agent_type_key.return_value = "knowledge"

    result = await binding_service.replace_skill_bindings(
        principal("agents.manage"),
        "tenant_test",
        "agent_test",
        ("skill_instruction",),
    )

    assert result.ids == ("skill_instruction",)
    skill_catalog.validate_instruction_only_ids.assert_awaited_once_with(
        "tenant_test", ("skill_instruction",)
    )
    skill_catalog.validate_ids.assert_not_awaited()
    repository.replace_skill_bindings.assert_awaited_once()


@pytest.mark.asyncio
async def test_agent_rejects_multiple_llm_bindings() -> None:
    binding_service, repository, llm_catalog, _, _ = service()

    with pytest.raises(AppError) as error:
        await binding_service.replace_llm_bindings(
            principal("agents.manage"),
            "tenant_test",
            "agent_test",
            ("llm_one", "llm_two"),
            "llm_one",
        )

    assert error.value.code == "AGENT_SINGLE_LLM_REQUIRED"
    llm_catalog.validate_ids.assert_not_awaited()
    repository.replace_llm_bindings.assert_not_awaited()


@pytest.mark.asyncio
async def test_default_llm_must_be_bound() -> None:
    binding_service, repository, _, _, _ = service()

    with pytest.raises(AppError) as error:
        await binding_service.replace_llm_bindings(
            principal("agents.manage"),
            "tenant_test",
            "agent_test",
            ("llm_one",),
            "llm_other",
        )

    assert error.value.code == "DEFAULT_LLM_NOT_BOUND"
    repository.replace_llm_bindings.assert_not_awaited()


@pytest.mark.asyncio
async def test_publish_readiness_requires_default_llm() -> None:
    binding_service, repository, _, _, _ = service()
    repository.get_llm_bindings.return_value = ((), None)

    with pytest.raises(AppError) as error:
        await binding_service.ensure_publishable("tenant_test", "agent_test")

    assert error.value.code == "AGENT_LLM_REQUIRED"


@pytest.mark.asyncio
async def test_publish_requires_dedicated_permission() -> None:
    database = SimpleNamespace(set_tenant=AsyncMock())
    agent_service = AgentService(
        cast(AsyncSession, SimpleNamespace()),
        cast(DatabaseManager, database),
    )

    with pytest.raises(AppError) as error:
        await agent_service.update(
            principal("agents.manage"),
            "tenant_test",
            "agent_test",
            AgentUpdateRequest(published=True),
        )

    assert error.value.code == "FORBIDDEN"
