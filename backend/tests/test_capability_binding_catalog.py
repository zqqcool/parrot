from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.mcp_servers.models import McpServer
from app.modules.mcp_servers.runtime_catalog import McpRuntimeCatalog
from app.modules.skills.models import Skill
from app.modules.skills.runtime_catalog import SkillRuntimeCatalog


@pytest.mark.asyncio
async def test_runtime_catalog_returns_only_explicitly_bound_tenant_skills() -> None:
    bound = Skill(
        id="skill_bound",
        tenant_id="tenant_test",
        name="tenant-report",
        description="Summarize reports",
        status="published",
        version=3,
        manifest={},
        instructions="Write a concise report.",
    )
    unbound = Skill(
        id="skill_unbound",
        tenant_id="tenant_test",
        name="tenant-search",
        description="Search trusted sources",
        status="published",
        version=1,
        manifest={},
        instructions="Search safely.",
    )
    session = SimpleNamespace(scalars=AsyncMock(return_value=[bound, unbound]))

    profiles = await SkillRuntimeCatalog(cast(AsyncSession, session)).get_published(
        "tenant_test", ("skill_bound",)
    )

    assert tuple(profile.id for profile in profiles) == ("skill_bound",)


@pytest.mark.asyncio
async def test_runtime_catalog_uses_published_package_without_a_build_artifact() -> None:
    skill = Skill(
        id="skill_direct",
        tenant_id="tenant_test",
        name="direct-skill",
        description="Run the published package directly",
        status="published",
        version=1,
        manifest={"runtime": {"entrypoint": "main.py"}},
        instructions="Return the test result.",
        package_path="tenant_test/skill_direct/1/source.zip",
        package_sha256="a" * 64,
    )
    session = SimpleNamespace(scalars=AsyncMock(return_value=[skill]))

    profiles = await SkillRuntimeCatalog(cast(AsyncSession, session)).get_published(
        "tenant_test", ("skill_direct",)
    )

    assert profiles[0].package_path == skill.package_path
    assert profiles[0].package_sha256 == skill.package_sha256


@pytest.mark.asyncio
async def test_runtime_catalog_returns_only_explicitly_bound_tenant_mcp_servers() -> None:
    bound = McpServer(
        id="mcp_bound",
        tenant_id="tenant_test",
        name="tenant-docs",
        transport="streamable_http",
        endpoint="https://mcp.example.test",
        arguments=[],
        encrypted_credentials=[],
        status="active",
    )
    unbound = McpServer(
        id="mcp_unbound",
        tenant_id="tenant_test",
        name="tenant-search",
        transport="streamable_http",
        endpoint="https://mcp.example.test",
        arguments=[],
        encrypted_credentials=[],
        status="active",
    )
    session = SimpleNamespace(scalars=AsyncMock(return_value=[bound, unbound]))

    profiles = await McpRuntimeCatalog(cast(AsyncSession, session)).get_active(
        "tenant_test", ("mcp_bound",)
    )

    assert tuple(profile.id for profile in profiles) == ("mcp_bound",)
