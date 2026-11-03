from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import socket
import tempfile
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.clock import SYSTEM_CLOCK, Clock
from app.core.config import AppConfig
from app.core.error_messages import public_error_message
from app.core.errors import AppError
from app.core.ids import new_id
from app.core.task_dispatch import TaskDispatcher
from app.infrastructure.db.session import DatabaseManager
from app.infrastructure.skill_package_storage import LocalSkillPackageStorage
from app.modules.audit.service import append_audit
from app.modules.capabilities.authorization import enter_tenant_capability_scope
from app.modules.iam.schemas import PrincipalContext
from app.modules.skills.build_artifact import build_runtime_artifact
from app.modules.skills.manifest import SkillManifest
from app.modules.skills.models import Skill, SkillBuildJob, SkillVersion
from app.modules.skills.package_service import SkillPackageService
from app.modules.skills.packages import inspect_skill_package
from app.modules.skills.schemas import SkillBuildView

logger = logging.getLogger(__name__)
_SKILL_BUILD_LEASE_DURATION = timedelta(minutes=20)


class SkillBuildService:
    def __init__(
        self,
        session: AsyncSession,
        database: DatabaseManager,
        dispatcher: TaskDispatcher | None = None,
    ) -> None:
        self._session = session
        self._database = database
        self._dispatcher = dispatcher

    async def request(
        self, principal: PrincipalContext, tenant_id: str, skill_id: str
    ) -> SkillBuildView:
        await enter_tenant_capability_scope(
            self._database, self._session, principal, tenant_id, "skills.manage", "Skill"
        )
        skill = await self._skill(tenant_id, skill_id, lock=True)
        draft = await self._draft(skill, lock=True)
        if draft is None:
            raise AppError(
                "SKILL_DRAFT_NOT_FOUND", "Skill has no editable draft", status.HTTP_409_CONFLICT
            )
        if not draft.package_sha256 or not draft.package_path:
            raise AppError(
                "SKILL_PACKAGE_REQUIRED",
                "Skill build requires a draft package",
                status.HTTP_422_UNPROCESSABLE_CONTENT,
            )
        if SkillManifest.parse(draft.manifest, allow_legacy=False).execution_spec is None:
            raise AppError(
                "SKILL_EXECUTION_NOT_CONFIGURED",
                "Instruction-only Skills do not require a build",
                status.HTTP_422_UNPROCESSABLE_CONTENT,
            )
        existing = await self._session.scalar(
            select(SkillBuildJob)
            .where(
                SkillBuildJob.tenant_id == tenant_id,
                SkillBuildJob.skill_version_id == draft.id,
                SkillBuildJob.source_checksum == draft.package_sha256,
            )
            .with_for_update()
        )
        artifact_is_current = (
            draft.runtime_artifact_path is not None
            and draft.runtime_artifact_sha256 is not None
            and draft.build_status == "succeeded"
            and draft.build_source_checksum == draft.package_sha256
        )
        if existing is None:
            job = SkillBuildJob(
                id=new_id("skill_build"),
                tenant_id=tenant_id,
                skill_version_id=draft.id,
                source_checksum=draft.package_sha256,
                status="queued",
            )
            self._session.add(job)
        else:
            job = existing
            if job.status == "failed" or (job.status == "succeeded" and not artifact_is_current):
                job.status = "queued"
                job.error_code = None
                job.lease_owner = None
                job.lease_until = None
        draft.build_status = job.status
        draft.build_source_checksum = draft.package_sha256
        await self._session.flush()
        if job.status == "queued" and self._dispatcher is not None:
            await self._dispatcher.dispatch_skill_build(tenant_id, job.id)
        append_audit(
            self._session,
            principal,
            "skill.draft.build.request",
            "skill",
            skill.id,
            {"draft_version_id": draft.id, "source_checksum": draft.package_sha256},
            tenant_id=tenant_id,
        )
        return skill_build_view(job, draft)

    async def get(
        self, principal: PrincipalContext, tenant_id: str, skill_id: str
    ) -> SkillBuildView | None:
        await enter_tenant_capability_scope(
            self._database, self._session, principal, tenant_id, "skills.read", "Skill"
        )
        skill = await self._skill(tenant_id, skill_id)
        draft = await self._draft(skill)
        if draft is None or not draft.build_source_checksum:
            return None
        job = await self._session.scalar(
            select(SkillBuildJob)
            .where(
                SkillBuildJob.tenant_id == tenant_id,
                SkillBuildJob.skill_version_id == draft.id,
                SkillBuildJob.source_checksum == draft.build_source_checksum,
            )
            .order_by(SkillBuildJob.created_at.desc())
        )
        return skill_build_view(job, draft) if job else None

    async def _skill(self, tenant_id: str, skill_id: str, *, lock: bool = False) -> Skill:
        statement = select(Skill).where(Skill.tenant_id == tenant_id, Skill.id == skill_id)
        if lock:
            statement = statement.with_for_update()
        skill = await self._session.scalar(statement)
        if skill is None:
            raise AppError("RESOURCE_NOT_FOUND", "Skill not found", status.HTTP_404_NOT_FOUND)
        return skill

    async def _draft(self, skill: Skill, *, lock: bool = False) -> SkillVersion | None:
        if not skill.draft_version_id:
            return None
        statement = select(SkillVersion).where(
            SkillVersion.tenant_id == skill.tenant_id,
            SkillVersion.skill_id == skill.id,
            SkillVersion.id == skill.draft_version_id,
        )
        if lock:
            statement = statement.with_for_update()
        return await self._session.scalar(statement)


@dataclass(frozen=True)
class ClaimedSkillBuild:
    id: str
    tenant_id: str
    skill_version_id: str
    source_checksum: str


class SkillBuildWorker:
    """TaskIQ-invoked Skill artifact builder."""

    def __init__(self, settings: AppConfig, *, clock: Clock = SYSTEM_CLOCK) -> None:
        self._settings = settings
        self._database = DatabaseManager(settings.database)
        self._source_storage = LocalSkillPackageStorage(settings.skills.package_directory)
        self._artifact_storage = LocalSkillPackageStorage(settings.skills.artifact_directory)
        self._packages = SkillPackageService(self._source_storage)
        self._clock = clock
        self._owner = f"{socket.gethostname()}:{os.getpid()}:taskiq-skill-build"

    async def close(self) -> None:
        await self._database.dispose()

    async def process(self, tenant_id: str, job_id: str) -> bool:
        claim = await self._claim(tenant_id, job_id)
        if claim is None:
            return False
        await self._build(claim)
        return True

    async def _claim(self, tenant_id: str, job_id: str) -> ClaimedSkillBuild | None:
        now = self._clock.now()
        async with self._database.session() as session:
            await self._database.set_tenant(session, tenant_id)
            job = await session.scalar(
                select(SkillBuildJob)
                .where(
                    SkillBuildJob.tenant_id == tenant_id,
                    SkillBuildJob.id == job_id,
                    SkillBuildJob.status.in_(("queued", "running")),
                    or_(SkillBuildJob.lease_until.is_(None), SkillBuildJob.lease_until < now),
                )
                .order_by(SkillBuildJob.created_at)
                .with_for_update(skip_locked=True)
            )
            if job is None:
                return None
            job.status = "running"
            job.lease_owner = self._owner
            job.lease_until = now + _SKILL_BUILD_LEASE_DURATION
            return ClaimedSkillBuild(job.id, tenant_id, job.skill_version_id, job.source_checksum)

    async def _build(self, claim: ClaimedSkillBuild) -> None:
        logger.info(
            "Skill build job started",
            extra={
                "tenant_id": claim.tenant_id,
                "skill_version_id": claim.skill_version_id,
                "job_id": claim.id,
            },
        )
        try:
            version = await self._version(claim)
            if version is None or version.package_sha256 != claim.source_checksum:
                await self._finish(claim, "failed", "SKILL_BUILD_SOURCE_CHANGED")
                return
            content = await self._packages.read(claim.tenant_id, version)
            package = await asyncio.to_thread(
                inspect_skill_package,
                version.package_filename or "skill.zip",
                content,
                self._settings.skills.max_package_bytes,
            )
            spec = SkillManifest.parse(package.manifest).execution_spec
            if spec is None:
                await self._finish(claim, "failed", "SKILL_EXECUTION_NOT_CONFIGURED")
                return
            self._settings.skills.build.session_directory.mkdir(
                mode=0o700, parents=True, exist_ok=True
            )
            with tempfile.TemporaryDirectory(
                prefix="skill-build-", dir=self._settings.skills.build.session_directory
            ) as temporary:
                artifact = await build_runtime_artifact(
                    content,
                    Path(temporary) / "source",
                    spec,
                    self._settings.skills.sandbox,
                    self._settings.skills.build,
                    self._settings.skills.max_package_bytes,
                    self._settings.skills.max_artifact_bytes,
                )
            checksum = hashlib.sha256(artifact).hexdigest()
            artifact_path = await self._artifact_storage.write(
                claim.tenant_id, version.skill_id, version.version, checksum, artifact
            )
            await self._succeed(claim, artifact_path, checksum, len(artifact))
            logger.info(
                "Skill build job completed",
                extra={
                    "tenant_id": claim.tenant_id,
                    "skill_version_id": claim.skill_version_id,
                    "job_id": claim.id,
                },
            )
        except AppError as error:
            await self._finish(claim, "failed", error.code)
        except Exception:
            logger.exception(
                "Skill dependency build failed",
                extra={"tenant_id": claim.tenant_id, "skill_version_id": claim.skill_version_id},
            )
            await self._finish(claim, "failed", "SKILL_BUILD_FAILED")

    async def _version(self, claim: ClaimedSkillBuild) -> SkillVersion | None:
        async with self._database.session() as session:
            await self._database.set_tenant(session, claim.tenant_id)
            return await session.scalar(
                select(SkillVersion).where(
                    SkillVersion.tenant_id == claim.tenant_id,
                    SkillVersion.id == claim.skill_version_id,
                )
            )

    async def _succeed(self, claim: ClaimedSkillBuild, path: str, checksum: str, size: int) -> None:
        async with self._database.session() as session:
            await self._database.set_tenant(session, claim.tenant_id)
            job = await session.scalar(select(SkillBuildJob).where(SkillBuildJob.id == claim.id))
            version = await session.scalar(
                select(SkillVersion).where(SkillVersion.id == claim.skill_version_id)
            )
            if job is None or version is None or version.package_sha256 != claim.source_checksum:
                return
            job.status = "succeeded"
            job.lease_owner = None
            job.lease_until = None
            version.build_status = "succeeded"
            version.build_source_checksum = claim.source_checksum
            version.runtime_artifact_path = path
            version.runtime_artifact_sha256 = checksum
            version.runtime_artifact_size_bytes = size

    async def _finish(self, claim: ClaimedSkillBuild, status_value: str, error_code: str) -> None:
        async with self._database.session() as session:
            await self._database.set_tenant(session, claim.tenant_id)
            job = await session.scalar(select(SkillBuildJob).where(SkillBuildJob.id == claim.id))
            version = await session.scalar(
                select(SkillVersion).where(SkillVersion.id == claim.skill_version_id)
            )
            if job is None:
                return
            job.status = status_value
            job.error_code = error_code
            job.lease_owner = None
            job.lease_until = None
            if version is not None and version.package_sha256 == claim.source_checksum:
                version.build_status = status_value
                version.build_source_checksum = claim.source_checksum


def skill_build_view(job: SkillBuildJob, version: SkillVersion) -> SkillBuildView:
    return SkillBuildView(
        id=job.id,
        source_checksum=job.source_checksum,
        status=job.status,
        error_code=job.error_code,
        failure_message=public_error_message(job.error_code) if job.error_code else None,
        artifact_sha256=version.runtime_artifact_sha256,
        artifact_size_bytes=version.runtime_artifact_size_bytes,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )
