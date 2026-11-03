from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
from _agent_runtime_support import credential_cipher
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import load_app_config
from app.core.errors import AppError
from app.infrastructure.db.session import DatabaseManager
from app.modules.iam.schemas import PrincipalContext
from app.modules.llm_configs.models import LlmConfig
from app.modules.llm_configs.service import LlmConfigService
from app.modules.mcp_servers.models import McpServer
from app.modules.mcp_servers.service import McpServerService
from app.modules.skills.models import Skill
from app.modules.skills.service import SkillService


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


@pytest.mark.asyncio
async def test_runtime_catalog_lists_tenant_owned_modules() -> None:
    llm = LlmConfig(
        id="llm_test",
        tenant_id="tenant_test",
        name="Primary",
        provider="openai-compatible",
        model="model-test",
        credential_envelope=None,
        temperature=0.2,
        max_tokens=4096,
        thinking_enabled=False,
        prompt_cache_enabled=False,
        status="active",
        is_default=True,
    )
    skill = Skill(
        id="skill_test",
        tenant_id="tenant_test",
        name="web-search",
        description="Search the web",
        status="published",
        version=2,
        manifest={},
        instructions="Use search safely",
    )
    mcp = McpServer(
        id="mcp_test",
        tenant_id="tenant_test",
        name="docs",
        transport="streamable_http",
        endpoint="https://mcp.example.test",
        arguments=[],
        encrypted_credentials=[],
        status="active",
    )
    database = cast(DatabaseManager, SimpleNamespace(set_tenant=AsyncMock()))
    llm_session = cast(AsyncSession, SimpleNamespace(scalars=AsyncMock(return_value=[llm])))
    llms = await LlmConfigService(
        llm_session, database, credential_cipher(), load_app_config()
    ).list(principal("llm_configs.read"), "tenant_test")
    skill_session = cast(AsyncSession, SimpleNamespace(scalars=AsyncMock(return_value=[skill])))
    skills = await SkillService(skill_session, database).list(
        principal("skills.read"), "tenant_test"
    )
    mcp_session = cast(AsyncSession, SimpleNamespace(scalars=AsyncMock(return_value=[mcp])))
    servers = await McpServerService(mcp_session, database, credential_cipher()).list(
        principal("mcp_servers.read"), "tenant_test"
    )

    assert llms[0].tenant_id == "tenant_test"
    assert llms[0].thinking_enabled is False
    assert llms[0].prompt_cache_enabled is False
    assert skills[0].tenant_id == "tenant_test"
    assert servers[0].tenant_id == "tenant_test"


@pytest.mark.asyncio
async def test_runtime_catalog_hides_other_tenant() -> None:
    service = SkillService(
        cast(AsyncSession, SimpleNamespace()), cast(DatabaseManager, SimpleNamespace())
    )
    with pytest.raises(AppError) as error:
        await service.list(principal("skills.read"), "tenant_other")
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_instruction_only_skill_validation_rejects_executable_skill() -> None:
    instruction = Skill(
        id="skill_instruction",
        tenant_id="tenant_test",
        name="instruction",
        description="",
        status="published",
        version=1,
        manifest={},
        instructions="Use the provided reference.",
    )
    executable = Skill(
        id="skill_executable",
        tenant_id="tenant_test",
        name="executable",
        description="",
        status="published",
        version=1,
        manifest={"runtime": {"type": "python", "entrypoint": "main.py"}},
        instructions="",
    )
    session = cast(
        AsyncSession, SimpleNamespace(scalars=AsyncMock(return_value=[instruction, executable]))
    )
    service = SkillService(session, cast(DatabaseManager, SimpleNamespace()))

    with pytest.raises(AppError) as error:
        await service.validate_instruction_only_ids("tenant_test", (instruction.id, executable.id))

    assert error.value.code == "KNOWLEDGE_AGENT_EXECUTABLE_SKILL_NOT_ALLOWED"
