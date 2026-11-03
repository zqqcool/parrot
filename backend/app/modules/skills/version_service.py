from __future__ import annotations

import asyncio
from collections.abc import Mapping

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.errors import AppError
from app.core.ids import new_id
from app.core.task_dispatch import TaskDispatcher
from app.infrastructure.db.session import DatabaseManager
from app.modules.audit.service import append_audit
from app.modules.capabilities.authorization import enter_tenant_capability_scope
from app.modules.iam.permissions import AGENTS_READ
from app.modules.iam.schemas import PrincipalContext, UserReference
from app.modules.iam.user_references import UserReferenceResolver
from app.modules.skills.bound_agents import SkillBoundAgent, SkillBoundAgentReader
from app.modules.skills.models import Skill, SkillVersion
from app.modules.skills.package_mutations import replace_skill_package_file
from app.modules.skills.package_service import (
    SkillPackageService,
    SkillPackageStorage,
    normalize_skill_package_import,
)
from app.modules.skills.packages import (
    inspect_skill_package,
    list_skill_package_files,
    read_skill_package_file,
)
from app.modules.skills.schemas import (
    SkillBoundAgentView,
    SkillFileContentView,
    SkillFileView,
    SkillVersionView,
    SkillView,
)

SkillVersionStorage = SkillPackageStorage


class SkillVersionService:
    def __init__(
        self,
        session: AsyncSession,
        database: DatabaseManager,
        package_storage: SkillVersionStorage,
        max_package_bytes: int,
        bound_agent_reader: SkillBoundAgentReader | None = None,
        dispatcher: TaskDispatcher | None = None,
    ) -> None:
        self.session = session
        self.database = database
        self._packages = SkillPackageService(package_storage)
        self.max_package_bytes = max_package_bytes
        self.bound_agent_reader = bound_agent_reader
        self._dispatcher = dispatcher

    async def get(self, principal: PrincipalContext, tenant_id: str, skill_id: str) -> SkillView:
        await self._enter(principal, tenant_id, "skills.read")
        return await self._skill_view(principal, await self._skill(tenant_id, skill_id))

    async def list_versions(
        self, principal: PrincipalContext, tenant_id: str, skill_id: str
    ) -> list[SkillVersionView]:
        await self._enter(principal, tenant_id, "skills.read")
        await self._skill(tenant_id, skill_id)
        rows = await self.session.scalars(
            select(SkillVersion)
            .join(Skill, Skill.id == SkillVersion.skill_id)
            .where(
                Skill.tenant_id == tenant_id,
                SkillVersion.skill_id == skill_id,
            )
            .order_by(SkillVersion.version.desc(), SkillVersion.created_at.desc())
        )
        return await self._version_views(list(rows))

    async def import_package(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        filename: str,
        content: bytes,
    ) -> SkillView:
        await self._enter(principal, tenant_id, "skills.manage")
        package, content = await asyncio.to_thread(
            normalize_skill_package_import, filename, content, self.max_package_bytes
        )
        skill = await self._skill_by_name(tenant_id, package.name)
        if skill is None:
            skill = Skill(
                id=new_id("skill"),
                tenant_id=tenant_id,
                created_by=principal.subject_id,
                name=package.name,
                status="draft",
            )
            self.session.add(skill)
            await self.session.flush()
        draft = await self._draft(skill)
        if draft is None:
            draft = SkillVersion(
                id=new_id("skill_version"),
                tenant_id=tenant_id,
                skill_id=skill.id,
                version=await self._next_version(skill.id),
                status="draft",
                created_by=principal.subject_id,
            )
            self.session.add(draft)
            skill.draft_version_id = draft.id
        await self._packages.set_version_package(skill, draft, package, content)
        if skill.current_version_id is None:
            self._project(skill, draft, status="draft")
        await self.session.flush()
        append_audit(
            self.session,
            principal,
            "skill.import",
            "skill",
            skill.id,
            {"filename": package.filename, "draft_version_id": draft.id},
            tenant_id=tenant_id,
        )
        return await self._skill_view(principal, skill)

    async def fork_draft(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        skill_id: str,
        source_version_id: str | None,
    ) -> SkillVersionView:
        await self._enter(principal, tenant_id, "skills.manage")
        skill = await self._skill(tenant_id, skill_id)
        source = await self._source_version(skill, source_version_id)
        draft = await self._draft(skill)
        if draft is not None:
            if draft.source_version_id == source.id:
                return await self._version_view(draft)
            raise AppError(
                "SKILL_DRAFT_EXISTS",
                "A draft already exists; finish or discard it before choosing another source "
                "version",
                status.HTTP_409_CONFLICT,
            )
        draft = SkillVersion(
            id=new_id("skill_version"),
            tenant_id=tenant_id,
            skill_id=skill.id,
            version=await self._next_version(skill.id),
            status="draft",
            description=source.description,
            manifest=source.manifest,
            instructions=source.instructions,
            package_path=source.package_path,
            package_filename=source.package_filename,
            package_size_bytes=source.package_size_bytes,
            package_sha256=source.package_sha256,
            source_version_id=source.id,
            created_by=principal.subject_id,
        )
        self.session.add(draft)
        skill.draft_version_id = draft.id
        await self.session.flush()
        append_audit(
            self.session,
            principal,
            "skill.draft.fork",
            "skill",
            skill.id,
            {"draft_version_id": draft.id, "source_version_id": source.id},
            tenant_id=tenant_id,
        )
        return await self._version_view(draft)

    async def publish(
        self, principal: PrincipalContext, tenant_id: str, skill_id: str
    ) -> SkillView:
        await self._enter(principal, tenant_id, "skills.manage")
        skill = await self._locked_skill(tenant_id, skill_id)
        draft = await self._locked_draft(skill)
        if draft is None:
            raise AppError(
                "SKILL_DRAFT_NOT_FOUND", "Skill has no draft to publish", status.HTTP_409_CONFLICT
            )
        if not draft.package_path:
            raise AppError(
                "SKILL_PACKAGE_REQUIRED",
                "Publish requires an imported Skill ZIP package",
                status.HTTP_422_UNPROCESSABLE_CONTENT,
            )
        await self._revalidate_publish_inputs(tenant_id, draft)
        draft.status = "published"
        draft.published_by = principal.subject_id
        draft.published_at = draft.updated_at
        skill.current_version_id = draft.id
        skill.draft_version_id = None
        self._project(skill, draft, status="published")
        await self.session.flush()
        await self._enqueue_index(skill)
        append_audit(
            self.session,
            principal,
            "skill.publish",
            "skill",
            skill.id,
            {"version_id": draft.id, "version": draft.version},
            tenant_id=tenant_id,
        )
        return await self._skill_view(principal, skill)

    async def rollback(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        skill_id: str,
        version_id: str,
    ) -> SkillView:
        await self._enter(principal, tenant_id, "skills.manage")
        skill = await self._skill(tenant_id, skill_id)
        version = await self._version(tenant_id, skill_id, version_id)
        if version.status != "published":
            raise AppError(
                "SKILL_VERSION_NOT_PUBLISHED",
                "Only published Skill versions can be restored",
                status.HTTP_422_UNPROCESSABLE_CONTENT,
            )
        skill.current_version_id = version.id
        self._project(skill, version, status="published")
        await self.session.flush()
        await self._enqueue_index(skill)
        append_audit(
            self.session,
            principal,
            "skill.rollback",
            "skill",
            skill.id,
            {"version_id": version.id, "version": version.version},
            tenant_id=tenant_id,
        )
        return await self._skill_view(principal, skill)

    async def list_files(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        skill_id: str,
        version_id: str,
    ) -> list[SkillFileView]:
        await self._enter(principal, tenant_id, "skills.read")
        version = await self._version(tenant_id, skill_id, version_id)
        content = await self._packages.read(tenant_id, version)
        files = await asyncio.to_thread(list_skill_package_files, content, self.max_package_bytes)
        return [SkillFileView.model_validate(item, from_attributes=True) for item in files]

    async def read_file(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        skill_id: str,
        version_id: str,
        file_path: str,
    ) -> SkillFileContentView:
        await self._enter(principal, tenant_id, "skills.read")
        version = await self._version(tenant_id, skill_id, version_id)
        content = await self._packages.read(tenant_id, version)
        value, file = await asyncio.to_thread(
            read_skill_package_file, content, file_path, self.max_package_bytes
        )
        return SkillFileContentView(
            path=file.path,
            size_bytes=file.size_bytes,
            editable=file.editable,
            content=value,
            checksum=version.package_sha256 or "",
        )

    async def write_draft_file(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        skill_id: str,
        file_path: str,
        content: str,
        expected_checksum: str,
    ) -> SkillFileContentView:
        await self._enter(principal, tenant_id, "skills.manage")
        skill = await self._skill(tenant_id, skill_id)
        draft = await self._draft(skill)
        if draft is None:
            raise AppError(
                "SKILL_DRAFT_NOT_FOUND", "Skill has no editable draft", status.HTTP_409_CONFLICT
            )
        if draft.package_sha256 != expected_checksum:
            raise AppError(
                "SKILL_DRAFT_CONFLICT",
                "Skill draft changed; refresh before saving",
                status.HTTP_409_CONFLICT,
            )
        archive = await self._packages.read(tenant_id, draft)
        rebuilt = await asyncio.to_thread(
            replace_skill_package_file, archive, file_path, content, self.max_package_bytes
        )
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
            "skill.draft.file.write",
            "skill",
            skill.id,
            {"draft_version_id": draft.id, "path": file_path},
            tenant_id=tenant_id,
        )
        return await self.read_file(principal, tenant_id, skill_id, draft.id, file_path)

    async def _skill(self, tenant_id: str, skill_id: str) -> Skill:
        skill = await self.session.scalar(
            select(Skill).where(Skill.tenant_id == tenant_id, Skill.id == skill_id)
        )
        if skill is None:
            raise AppError("RESOURCE_NOT_FOUND", "Skill not found", status.HTTP_404_NOT_FOUND)
        return skill

    async def _locked_skill(self, tenant_id: str, skill_id: str) -> Skill:
        skill = await self.session.scalar(
            select(Skill)
            .where(Skill.tenant_id == tenant_id, Skill.id == skill_id)
            .with_for_update()
        )
        if skill is None:
            raise AppError("RESOURCE_NOT_FOUND", "Skill not found", status.HTTP_404_NOT_FOUND)
        return skill

    async def _skill_by_name(self, tenant_id: str, name: str) -> Skill | None:
        return await self.session.scalar(
            select(Skill).where(Skill.tenant_id == tenant_id, Skill.name == name)
        )

    async def _version(self, tenant_id: str, skill_id: str, version_id: str) -> SkillVersion:
        version = await self.session.scalar(
            select(SkillVersion)
            .join(Skill, Skill.id == SkillVersion.skill_id)
            .where(
                Skill.tenant_id == tenant_id,
                SkillVersion.skill_id == skill_id,
                SkillVersion.id == version_id,
            )
        )
        if version is None:
            raise AppError(
                "RESOURCE_NOT_FOUND", "Skill version not found", status.HTTP_404_NOT_FOUND
            )
        return version

    async def _draft(self, skill: Skill) -> SkillVersion | None:
        if not skill.draft_version_id:
            return None
        return await self._version(skill.tenant_id, skill.id, skill.draft_version_id)

    async def _locked_draft(self, skill: Skill) -> SkillVersion | None:
        if not skill.draft_version_id:
            return None
        return await self.session.scalar(
            select(SkillVersion)
            .where(
                SkillVersion.tenant_id == skill.tenant_id,
                SkillVersion.skill_id == skill.id,
                SkillVersion.id == skill.draft_version_id,
            )
            .with_for_update()
        )

    async def _revalidate_publish_inputs(self, tenant_id: str, draft: SkillVersion) -> None:
        content = await self._packages.read(tenant_id, draft)
        package = await asyncio.to_thread(
            inspect_skill_package,
            draft.package_filename or "skill.zip",
            content,
            self.max_package_bytes,
        )
        if package.sha256 != draft.package_sha256:
            raise AppError(
                "SKILL_PACKAGE_CHANGED",
                "Skill draft integrity check failed",
                status.HTTP_409_CONFLICT,
            )

    async def _source_version(self, skill: Skill, version_id: str | None) -> SkillVersion:
        selected_id = version_id or skill.current_version_id
        if not selected_id:
            raise AppError(
                "SKILL_VERSION_NOT_FOUND",
                "Skill has no published version to use as a draft source",
                status.HTTP_409_CONFLICT,
            )
        source = await self._version(skill.tenant_id, skill.id, selected_id)
        if source.status != "published":
            raise AppError(
                "SKILL_VERSION_NOT_PUBLISHED",
                "Only published Skill versions can be used as a draft source",
                status.HTTP_422_UNPROCESSABLE_CONTENT,
            )
        return source

    async def _next_version(self, skill_id: str) -> int:
        latest = await self.session.scalar(
            select(func.max(SkillVersion.version)).where(SkillVersion.skill_id == skill_id)
        )
        return int(latest or 0) + 1

    async def _enter(self, principal: PrincipalContext, tenant_id: str, permission: str) -> None:
        await enter_tenant_capability_scope(
            self.database, self.session, principal, tenant_id, permission, "Skill"
        )

    @staticmethod
    def _project(skill: Skill, version: SkillVersion, *, status: str) -> None:
        skill.status = status
        skill.version = version.version
        skill.description = version.description
        skill.manifest = version.manifest
        skill.instructions = version.instructions
        skill.package_path = version.package_path
        skill.package_filename = version.package_filename
        skill.package_size_bytes = version.package_size_bytes
        skill.package_sha256 = version.package_sha256
        skill.runtime_artifact_path = version.runtime_artifact_path
        skill.runtime_artifact_sha256 = version.runtime_artifact_sha256
        skill.runtime_artifact_size_bytes = version.runtime_artifact_size_bytes
        skill.build_status = version.build_status
        skill.build_source_checksum = version.build_source_checksum

    async def _enqueue_index(self, item: Skill) -> None:
        if self._dispatcher is None:
            return
        await self._dispatcher.dispatch_capability_index(
            item.tenant_id, "skill", item.id, str(item.version)
        )

    async def _skill_view(self, principal: PrincipalContext, item: Skill) -> SkillView:
        users = await UserReferenceResolver(self.session).resolve(
            item.tenant_id, (item.created_by,)
        )
        bound_agents = await self._bound_agents(principal, item)
        return self.skill_view(item, users, bound_agents)

    async def _bound_agents(
        self, principal: PrincipalContext, item: Skill
    ) -> tuple[SkillBoundAgent, ...] | None:
        if AGENTS_READ not in principal.permissions:
            return None
        if self.bound_agent_reader is None:
            return ()
        bound_agents = await self.bound_agent_reader.list_bound_agents(item.tenant_id, (item.id,))
        return bound_agents.get(item.id, ())

    async def _version_view(self, item: SkillVersion) -> SkillVersionView:
        users = await UserReferenceResolver(self.session).resolve(
            item.tenant_id, (item.created_by, item.published_by)
        )
        return self.version_view(item, users)

    async def _version_views(self, items: list[SkillVersion]) -> list[SkillVersionView]:
        users = await UserReferenceResolver(self.session).resolve(
            items[0].tenant_id if items else None,
            (user_id for item in items for user_id in (item.created_by, item.published_by)),
        )
        return [self.version_view(item, users) for item in items]

    @staticmethod
    def skill_view(
        item: Skill,
        users: Mapping[str, UserReference] | None = None,
        bound_agents: tuple[SkillBoundAgent, ...] | None = None,
    ) -> SkillView:
        view = SkillView.model_validate(item, from_attributes=True)
        return view.model_copy(
            update={
                "created_by_user": (users or {}).get(item.created_by or ""),
                "has_draft": bool(item.draft_version_id),
                "bound_agents": (
                    tuple(
                        SkillBoundAgentView(
                            id=agent.id,
                            name=agent.name,
                        )
                        for agent in bound_agents
                    )
                    if bound_agents is not None
                    else None
                ),
            }
        )

    @staticmethod
    def version_view(
        item: SkillVersion, users: Mapping[str, UserReference] | None = None
    ) -> SkillVersionView:
        view = SkillVersionView.model_validate(item, from_attributes=True)
        return view.model_copy(
            update={
                "created_by_user": (users or {}).get(item.created_by or ""),
                "published_by_user": (users or {}).get(item.published_by or ""),
            }
        )
