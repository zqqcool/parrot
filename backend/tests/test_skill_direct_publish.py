from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.session import DatabaseManager
from app.modules.iam.schemas import PrincipalContext
from app.modules.skills.models import Skill, SkillVersion
from app.modules.skills.package_service import SkillPackageStorage
from app.modules.skills.schemas import SkillView
from app.modules.skills.version_service import SkillVersionService


class _Session:
    def __init__(self) -> None:
        self.flushed = False

    def add(self, _item: object) -> None:
        return None

    async def flush(self) -> None:
        self.flushed = True


class _Storage:
    async def write(
        self, tenant_id: str, skill_id: str, version: int, checksum: str, content: bytes
    ) -> str:
        return f"{tenant_id}/{skill_id}/{version}/{checksum}/{len(content)}"

    async def read(self, package_path: str) -> bytes:
        raise AssertionError(f"unexpected package read: {package_path}")


class _DirectPublishService(SkillVersionService):
    def __init__(
        self, session: AsyncSession, skill: Skill, draft: SkillVersion, result: SkillView
    ) -> None:
        super().__init__(
            session,
            cast(DatabaseManager, SimpleNamespace()),
            cast(SkillPackageStorage, _Storage()),
            1024,
        )
        self._test_skill = skill
        self._test_draft = draft
        self._test_result = result

    async def _enter(self, principal: PrincipalContext, tenant_id: str, permission: str) -> None:
        return None

    async def _locked_skill(self, tenant_id: str, skill_id: str) -> Skill:
        return self._test_skill

    async def _locked_draft(self, skill: Skill) -> SkillVersion:
        return self._test_draft

    async def _revalidate_publish_inputs(self, tenant_id: str, draft: SkillVersion) -> None:
        return None

    async def _skill_view(self, principal: PrincipalContext, item: Skill) -> SkillView:
        return self._test_result


@pytest.mark.asyncio
async def test_publish_executable_draft_does_not_require_a_build_artifact() -> None:
    now = datetime(2026, 7, 16, tzinfo=UTC)
    skill = Skill(
        id="skill_test",
        tenant_id="tenant_test",
        name="direct-publish",
        description="",
        instructions="",
        draft_version_id="skill_version_test",
    )
    draft = SkillVersion(
        id="skill_version_test",
        tenant_id="tenant_test",
        skill_id=skill.id,
        version=1,
        status="draft",
        manifest={"runtime": {"entrypoint": "main.py"}},
        instructions="Run the test entrypoint.",
        package_path="tenant_test/skill_test/1/source.zip",
        package_sha256="a" * 64,
        build_status="failed",
        created_at=now,
        updated_at=now,
    )
    session = _Session()
    result = SkillView(
        id=skill.id,
        tenant_id=skill.tenant_id,
        name=skill.name,
        description=skill.description,
        status="published",
        version=draft.version,
        manifest=draft.manifest,
        instructions=draft.instructions,
    )
    service = _DirectPublishService(
        cast(AsyncSession, session),
        skill,
        draft,
        result,
    )
    principal = PrincipalContext(
        tenant_id="tenant_test",
        subject_id="user_test",
        username="test",
        display_name="Test",
        permissions=("skills.manage",),
        tenants=(),
        must_change_password=False,
        request_id="req_test",
    )

    published = await service.publish(principal, "tenant_test", skill.id)

    assert published == result
    assert draft.status == "published"
    assert skill.current_version_id == draft.id
    assert skill.draft_version_id is None
    assert session.flushed is True
