from __future__ import annotations

import asyncio
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.errors import AppError
from app.infrastructure.db.session import DatabaseManager
from app.modules.audit.service import append_audit
from app.modules.capabilities.authorization import enter_tenant_capability_scope
from app.modules.iam.schemas import PrincipalContext
from app.modules.skills.models import Skill, SkillVersion
from app.modules.skills.package_mutations import (
    create_skill_package_directory,
    create_skill_package_file,
    delete_skill_package_entry,
)
from app.modules.skills.package_service import SkillPackageService, SkillPackageStorage
from app.modules.skills.packages import inspect_skill_package
from app.modules.skills.schemas import SkillDraftEntryMutationView


class SkillDraftEntryService:
    def __init__(
        self,
        session: AsyncSession,
        database: DatabaseManager,
        package_storage: SkillPackageStorage,
        max_package_bytes: int,
    ) -> None:
        self.session = session
        self.database = database
        self._packages = SkillPackageService(package_storage)
        self.max_package_bytes = max_package_bytes

    async def create_file(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        skill_id: str,
        path: str,
        content: str,
        expected_checksum: str,
    ) -> SkillDraftEntryMutationView:
        return await self._mutate(
            principal, tenant_id, skill_id, path, expected_checksum, "file.create", content
        )

    async def create_directory(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        skill_id: str,
        path: str,
        expected_checksum: str,
    ) -> SkillDraftEntryMutationView:
        return await self._mutate(
            principal, tenant_id, skill_id, path, expected_checksum, "directory.create", None
        )

    async def delete(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        skill_id: str,
        path: str,
        expected_checksum: str,
    ) -> SkillDraftEntryMutationView:
        return await self._mutate(
            principal, tenant_id, skill_id, path, expected_checksum, "entry.delete", None
        )

    async def _mutate(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        skill_id: str,
        path: str,
        expected_checksum: str,
        action: Literal["file.create", "directory.create", "entry.delete"],
        content: str | None,
    ) -> SkillDraftEntryMutationView:
        await enter_tenant_capability_scope(
            self.database, self.session, principal, tenant_id, "skills.manage", "Skill"
        )
        skill = await self._skill(tenant_id, skill_id)
        draft = await self._draft(skill)
        if draft.package_sha256 != expected_checksum:
            raise AppError(
                "SKILL_DRAFT_CONFLICT",
                "Skill draft changed; refresh before saving",
                status.HTTP_409_CONFLICT,
            )
        archive = await self._packages.read(tenant_id, draft)
        rebuilt = await asyncio.to_thread(self._apply, action, archive, path, content)
        package = await asyncio.to_thread(
            inspect_skill_package,
            draft.package_filename or "skill.zip",
            rebuilt,
            self.max_package_bytes,
        )
        await self._packages.set_version_package(skill, draft, package, rebuilt)
        await self.session.flush()
        append_audit(
            self.session,
            principal,
            f"skill.draft.{action}",
            "skill",
            skill.id,
            {"draft_version_id": draft.id, "path": path},
            tenant_id=tenant_id,
        )
        return SkillDraftEntryMutationView(path=path, checksum=draft.package_sha256 or "")

    def _apply(
        self,
        action: Literal["file.create", "directory.create", "entry.delete"],
        archive: bytes,
        path: str,
        content: str | None,
    ) -> bytes:
        if action == "file.create":
            return create_skill_package_file(archive, path, content or "", self.max_package_bytes)
        if action == "directory.create":
            return create_skill_package_directory(archive, path, self.max_package_bytes)
        return delete_skill_package_entry(archive, path, self.max_package_bytes)

    async def _skill(self, tenant_id: str, skill_id: str) -> Skill:
        skill = await self.session.scalar(
            select(Skill).where(Skill.tenant_id == tenant_id, Skill.id == skill_id)
        )
        if skill is None:
            raise AppError("RESOURCE_NOT_FOUND", "Skill not found", status.HTTP_404_NOT_FOUND)
        return skill

    async def _draft(self, skill: Skill) -> SkillVersion:
        if not skill.draft_version_id:
            raise AppError(
                "SKILL_DRAFT_NOT_FOUND", "Skill has no editable draft", status.HTTP_409_CONFLICT
            )
        draft = await self.session.scalar(
            select(SkillVersion).where(
                SkillVersion.id == skill.draft_version_id,
                SkillVersion.skill_id == skill.id,
            )
        )
        if draft is None:
            raise AppError(
                "SKILL_DRAFT_NOT_FOUND", "Skill has no editable draft", status.HTTP_409_CONFLICT
            )
        return draft
