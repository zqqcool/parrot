from __future__ import annotations

import logging
from typing import Protocol

from starlette import status

from app.core.errors import AppError
from app.modules.skills.models import Skill, SkillVersion
from app.modules.skills.package_mutations import materialize_default_skill_package_manifest
from app.modules.skills.packages import SkillPackage, inspect_skill_package

logger = logging.getLogger(__name__)


def normalize_skill_package_import(
    filename: str, content: bytes, max_package_bytes: int
) -> tuple[SkillPackage, bytes]:
    """Validate an uploaded package and persist an explicit default manifest when omitted."""
    package = inspect_skill_package(filename, content, max_package_bytes)
    normalized_content = materialize_default_skill_package_manifest(content, max_package_bytes)
    if normalized_content == content:
        return package, content
    return inspect_skill_package(
        filename, normalized_content, max_package_bytes
    ), normalized_content


class SkillPackageStorage(Protocol):
    async def write(
        self, tenant_id: str, skill_id: str, version: int, checksum: str, content: bytes
    ) -> str: ...

    async def read(self, package_path: str) -> bytes: ...


class SkillPackageService:
    """Owns durable Skill archive storage and version package metadata."""

    def __init__(self, storage: SkillPackageStorage) -> None:
        self._storage = storage

    async def set_version_package(
        self, skill: Skill, version: SkillVersion, package: SkillPackage, content: bytes
    ) -> None:
        version.package_path = await self._store(skill, version, package, content)
        version.description = package.description
        version.manifest = package.manifest
        version.instructions = package.instructions
        version.package_filename = package.filename
        version.package_size_bytes = package.size_bytes
        version.package_sha256 = package.sha256
        version.runtime_artifact_path = None
        version.runtime_artifact_sha256 = None
        version.runtime_artifact_size_bytes = None
        version.build_status = None
        version.build_source_checksum = None

    async def read(self, tenant_id: str, version: SkillVersion) -> bytes:
        if not version.package_path:
            raise AppError(
                "SKILL_PACKAGE_NOT_FOUND", "Skill package is unavailable", status.HTTP_404_NOT_FOUND
            )
        return await self.read_path(tenant_id, version.package_path)

    async def read_path(self, tenant_id: str, package_path: str) -> bytes:
        try:
            return await self._storage.read(package_path)
        except OSError as error:
            logger.exception("Skill package read failed", extra={"tenant_id": tenant_id})
            raise AppError(
                "SKILL_STORAGE_UNAVAILABLE",
                "Skill package storage is temporarily unavailable",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            ) from error

    async def _store(
        self, skill: Skill, version: SkillVersion, package: SkillPackage, content: bytes
    ) -> str:
        try:
            return await self._storage.write(
                skill.tenant_id,
                skill.id,
                version.version,
                package.sha256,
                content,
            )
        except OSError as error:
            logger.exception("Skill package storage failed", extra={"tenant_id": skill.tenant_id})
            raise AppError(
                "SKILL_STORAGE_UNAVAILABLE",
                "Skill package storage is temporarily unavailable",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            ) from error
