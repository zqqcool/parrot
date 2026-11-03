from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from typing import Protocol, cast

from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
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
from app.modules.skills.deletion import SkillDeletionGuard
from app.modules.skills.manifest import SkillManifest
from app.modules.skills.models import Skill
from app.modules.skills.package_service import normalize_skill_package_import
from app.modules.skills.packages import SkillPackage
from app.modules.skills.schemas import (
    SkillBoundAgentView,
    SkillCreateRequest,
    SkillUpdateRequest,
    SkillView,
)

logger = logging.getLogger(__name__)


class SkillPackageStorage(Protocol):
    async def write(
        self,
        tenant_id: str,
        skill_id: str,
        version: int,
        checksum: str,
        content: bytes,
    ) -> str: ...


class SkillService:
    def __init__(
        self,
        session: AsyncSession,
        database: DatabaseManager,
        package_storage: SkillPackageStorage | None = None,
        max_package_bytes: int = 50 * 1024 * 1024,
        deletion_guard: SkillDeletionGuard | None = None,
        bound_agent_reader: SkillBoundAgentReader | None = None,
        dispatcher: TaskDispatcher | None = None,
    ) -> None:
        self.session = session
        self.database = database
        self.package_storage = package_storage
        self.max_package_bytes = max_package_bytes
        self.deletion_guard = deletion_guard
        self.bound_agent_reader = bound_agent_reader
        self._dispatcher = dispatcher

    async def list(
        self, principal: PrincipalContext, tenant_id: str, *, query: str | None = None
    ) -> list[SkillView]:
        await self._enter(principal, tenant_id, "skills.read")
        statement = select(Skill).where(Skill.tenant_id == tenant_id)
        normalized = query.strip() if query else ""
        if normalized:
            statement = statement.where(
                or_(
                    Skill.name.icontains(normalized, autoescape=True),
                    Skill.description.icontains(normalized, autoescape=True),
                )
            )
        rows = await self.session.scalars(statement.order_by(Skill.name))
        return await self._views(principal, list(rows))

    async def validate_ids(self, tenant_id: str, ids: tuple[str, ...]) -> None:
        if not ids:
            return
        found = await self.session.scalars(
            select(Skill.id).where(
                Skill.tenant_id == tenant_id,
                Skill.id.in_(ids),
                Skill.status == "published",
            )
        )
        if set(found) != set(ids):
            raise AppError(
                "SKILL_NOT_FOUND",
                "One or more published skills are unavailable",
                status.HTTP_404_NOT_FOUND,
            )

    async def validate_instruction_only_ids(self, tenant_id: str, ids: tuple[str, ...]) -> None:
        if not ids:
            return
        rows = await self.session.scalars(
            select(Skill).where(
                Skill.tenant_id == tenant_id,
                Skill.id.in_(ids),
                Skill.status == "published",
            )
        )
        skills = {item.id: item for item in rows}
        if set(skills) != set(ids):
            raise AppError(
                "SKILL_NOT_FOUND",
                "One or more published skills are unavailable",
                status.HTTP_404_NOT_FOUND,
            )
        if any(_skill_is_executable(skills[skill_id].manifest) for skill_id in ids):
            raise AppError(
                "KNOWLEDGE_AGENT_EXECUTABLE_SKILL_NOT_ALLOWED",
                "Knowledge Agents may bind instruction-only Skills only",
                status.HTTP_422_UNPROCESSABLE_CONTENT,
            )

    async def create(
        self, principal: PrincipalContext, tenant_id: str, payload: SkillCreateRequest
    ) -> SkillView:
        await self._enter(principal, tenant_id, "skills.manage")
        values = payload.model_dump()
        values["manifest"] = SkillManifest.parse(
            payload.manifest, allow_legacy=False
        ).to_current_mapping()
        model = Skill(
            id=new_id("skill"),
            tenant_id=tenant_id,
            created_by=principal.subject_id,
            **values,
        )
        self.session.add(model)
        await self.session.flush()
        if model.status == "published":
            await self._enqueue_index(model)
        append_audit(
            self.session, principal, "skill.create", "skill", model.id, tenant_id=tenant_id
        )
        return await self._view(principal, model)

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
        model = await self._draft_for_package(tenant_id, package)
        await self.session.flush()
        model.package_path = await self._store_package(tenant_id, model, package, content)
        model.package_filename = package.filename
        model.package_size_bytes = package.size_bytes
        model.package_sha256 = package.sha256
        await self.session.flush()
        append_audit(
            self.session,
            principal,
            "skill.import",
            "skill",
            model.id,
            {"filename": package.filename, "size_bytes": package.size_bytes},
            tenant_id=tenant_id,
        )
        return await self._view(principal, model)

    async def update(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        skill_id: str,
        payload: SkillUpdateRequest,
    ) -> SkillView:
        await self._enter(principal, tenant_id, "skills.manage")
        model = await self._get(tenant_id, skill_id)
        values = payload.model_dump(exclude_unset=True)
        if "manifest" in values and values["manifest"] is not None:
            values["manifest"] = SkillManifest.parse(
                cast(dict[str, object], values["manifest"]), allow_legacy=False
            ).to_current_mapping()
        if values.get("status") == "published" and not model.package_path:
            raise AppError(
                "SKILL_PACKAGE_REQUIRED",
                "Publish requires an imported Skill ZIP package",
                status.HTTP_422_UNPROCESSABLE_CONTENT,
            )
        if values and any(key in values for key in ("manifest", "instructions")):
            values["version"] = model.version + 1
        if values:
            await self.session.execute(update(Skill).where(Skill.id == skill_id).values(**values))
            await self.session.refresh(model)
            if model.status == "published":
                await self._enqueue_index(model)
        append_audit(
            self.session, principal, "skill.update", "skill", model.id, values, tenant_id=tenant_id
        )
        return await self._view(principal, model)

    async def delete(self, principal: PrincipalContext, tenant_id: str, skill_id: str) -> None:
        await self._enter(principal, tenant_id, "skills.manage")
        model = await self._get(tenant_id, skill_id)
        indexed_revision = str(model.version)
        if self.deletion_guard is None:
            raise RuntimeError("Skill deletion guard is not configured")
        if await self.deletion_guard.is_bound_to_agent(tenant_id, skill_id):
            raise AppError(
                "SKILL_IN_USE",
                "该 Skill 仍被智能体绑定，请先解除关联后再删除",
                status.HTTP_409_CONFLICT,
            )
        await self.session.delete(model)
        try:
            await self.session.flush()
        except IntegrityError as error:
            raise AppError(
                "SKILL_IN_USE",
                "该 Skill 仍被智能体绑定，请先解除关联后再删除",
                status.HTTP_409_CONFLICT,
            ) from error
        append_audit(
            self.session,
            principal,
            "skill.delete",
            "skill",
            skill_id,
            {"name": model.name},
            tenant_id=tenant_id,
        )
        if self._dispatcher is not None:
            await self._dispatcher.dispatch_capability_index(
                tenant_id, "skill", skill_id, indexed_revision
            )

    async def _enqueue_index(self, item: Skill) -> None:
        if self._dispatcher is None:
            return
        await self._dispatcher.dispatch_capability_index(
            item.tenant_id, "skill", item.id, str(item.version)
        )

    async def _draft_for_package(self, tenant_id: str, package: SkillPackage) -> Skill:
        model = await self.session.scalar(
            select(Skill).where(
                Skill.tenant_id == tenant_id,
                Skill.name == package.name,
            )
        )
        if model is None:
            model = Skill(
                id=new_id("skill"),
                tenant_id=tenant_id,
                name=package.name,
                description=package.description,
                status="draft",
                manifest=package.manifest,
                instructions=package.instructions,
            )
            self.session.add(model)
            return model
        if model.status != "draft":
            raise AppError(
                "SKILL_PUBLISHED_IMMUTABLE",
                "Published Skill packages are immutable; import a new Skill with a different name.",
                status.HTTP_409_CONFLICT,
            )
        model.description = package.description
        model.manifest = package.manifest
        model.instructions = package.instructions
        model.version += 1
        return model

    async def _store_package(
        self, tenant_id: str, model: Skill, package: SkillPackage, content: bytes
    ) -> str:
        if self.package_storage is None:
            raise RuntimeError("Skill package storage is not configured")
        try:
            return await self.package_storage.write(
                tenant_id,
                model.id,
                model.version,
                package.sha256,
                content,
            )
        except OSError as error:
            logger.exception("Skill package storage failed", extra={"tenant_id": tenant_id})
            raise AppError(
                "SKILL_STORAGE_UNAVAILABLE",
                "Skill package storage is temporarily unavailable",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            ) from error

    async def _get(self, tenant_id: str, skill_id: str) -> Skill:
        model = await self.session.scalar(
            select(Skill).where(Skill.tenant_id == tenant_id, Skill.id == skill_id)
        )
        if model is None:
            raise AppError("RESOURCE_NOT_FOUND", "Skill not found", status.HTTP_404_NOT_FOUND)
        return model

    async def _enter(self, principal: PrincipalContext, tenant_id: str, permission: str) -> None:
        await enter_tenant_capability_scope(
            self.database, self.session, principal, tenant_id, permission, "Skill"
        )

    async def _view(self, principal: PrincipalContext, item: Skill) -> SkillView:
        users = await UserReferenceResolver(self.session).resolve(
            item.tenant_id, (item.created_by,)
        )
        bound_agents = await self._bound_agents(principal, item.tenant_id, (item.id,))
        return self.view(
            item,
            users,
            bound_agents.get(item.id, ()) if bound_agents is not None else None,
        )

    async def _views(self, principal: PrincipalContext, items: list[Skill]) -> list[SkillView]:
        users = await UserReferenceResolver(self.session).resolve(
            items[0].tenant_id if items else None, (item.created_by for item in items)
        )
        tenant_id = items[0].tenant_id if items else ""
        bound_agents = await self._bound_agents(
            principal, tenant_id, tuple(item.id for item in items)
        )
        return [
            self.view(
                item,
                users,
                bound_agents.get(item.id, ()) if bound_agents is not None else None,
            )
            for item in items
        ]

    async def _bound_agents(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        skill_ids: tuple[str, ...],
    ) -> Mapping[str, tuple[SkillBoundAgent, ...]] | None:
        if AGENTS_READ not in principal.permissions:
            return None
        if not skill_ids or self.bound_agent_reader is None:
            return {}
        return await self.bound_agent_reader.list_bound_agents(tenant_id, skill_ids)

    @staticmethod
    def view(
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


def _skill_is_executable(manifest: dict[str, object]) -> bool:
    return SkillManifest.parse(manifest).execution_spec is not None
