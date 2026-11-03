from __future__ import annotations

import io
import zipfile

from starlette import status

from app.core.errors import AppError
from app.modules.skills.manifest import MANIFEST_FILENAME, SkillManifest
from app.modules.skills.packages import (
    MAX_SKILL_TEXT_FILE_BYTES,
    inspect_skill_package,
    join_skill_package_root,
    normalize_skill_package_path,
    open_skill_package_archive,
    resolve_existing_skill_package_path,
    skill_package_directories,
    skill_package_validation_error,
)


def create_skill_package_file(
    content: bytes, relative_path: str, text: str, max_package_bytes: int
) -> bytes:
    requested = normalize_skill_package_path(relative_path)
    if requested == MANIFEST_FILENAME:
        manifest = SkillManifest.from_json(text, allow_legacy=False)
        return add_skill_package_manifest(content, manifest, max_package_bytes)
    return _create_file(content, requested, text.encode("utf-8"), max_package_bytes)


def add_skill_package_manifest(
    content: bytes, manifest: SkillManifest, max_package_bytes: int
) -> bytes:
    """Add the optional root manifest through the canonical manifest serializer."""
    return _create_file(
        content,
        MANIFEST_FILENAME,
        manifest.to_current_json().encode("utf-8"),
        max_package_bytes,
    )


def materialize_default_skill_package_manifest(content: bytes, max_package_bytes: int) -> bytes:
    """Add the canonical instruction-only manifest when an imported package omits it."""
    archive, files, root = open_skill_package_archive(content, max_package_bytes)
    with archive:
        if join_skill_package_root(root, MANIFEST_FILENAME) in files:
            return content
    return add_skill_package_manifest(content, SkillManifest.instruction_only(), max_package_bytes)


def replace_skill_package_file(
    content: bytes,
    relative_path: str,
    replacement: str,
    max_package_bytes: int,
) -> bytes:
    requested = normalize_skill_package_path(relative_path)
    if requested == MANIFEST_FILENAME:
        manifest = SkillManifest.from_json(replacement, allow_legacy=False)
        return replace_skill_package_manifest(content, manifest, max_package_bytes)
    return _replace_file(content, requested, replacement.encode("utf-8"), max_package_bytes)


def replace_skill_package_manifest(
    content: bytes, manifest: SkillManifest, max_package_bytes: int
) -> bytes:
    """Change a manifest only after parsing and serializing it through SkillManifest."""
    return _replace_file(
        content,
        MANIFEST_FILENAME,
        manifest.to_current_json().encode("utf-8"),
        max_package_bytes,
    )


def delete_skill_package_entry(content: bytes, relative_path: str, max_package_bytes: int) -> bytes:
    requested = normalize_skill_package_path(relative_path)
    if requested == MANIFEST_FILENAME:
        return remove_skill_package_manifest(content, max_package_bytes)
    return _delete_entry(content, requested, max_package_bytes)


def remove_skill_package_manifest(content: bytes, max_package_bytes: int) -> bytes:
    """Remove the optional root manifest through its dedicated mutation path."""
    return _delete_entry(content, MANIFEST_FILENAME, max_package_bytes)


def _create_file(
    content: bytes, requested: str, replacement: bytes, max_package_bytes: int
) -> bytes:
    archive, files, root = open_skill_package_archive(content, max_package_bytes)
    with archive:
        archive_path = join_skill_package_root(root, requested)
        directories = skill_package_directories(archive)
        if archive_path in files or archive_path in directories:
            raise AppError(
                "SKILL_ENTRY_EXISTS", "Skill entry already exists", status.HTTP_409_CONFLICT
            )
        if len(replacement) > MAX_SKILL_TEXT_FILE_BYTES:
            raise skill_package_validation_error("Skill file exceeds the editable size limit")
        return _rebuild(
            archive, files, directories, {archive_path: replacement}, set(), max_package_bytes
        )


def _replace_file(
    content: bytes, requested: str, replacement: bytes, max_package_bytes: int
) -> bytes:
    archive, files, root = open_skill_package_archive(content, max_package_bytes)
    with archive:
        archive_path = resolve_existing_skill_package_path(root, requested, files)
        member = files.get(archive_path)
        if member is None:
            raise AppError("RESOURCE_NOT_FOUND", "Skill file not found", status.HTTP_404_NOT_FOUND)
        if not _is_utf8_text(archive.read(member), member.file_size):
            raise skill_package_validation_error("Skill file is not editable UTF-8 text")
        if len(replacement) > MAX_SKILL_TEXT_FILE_BYTES:
            raise skill_package_validation_error("Skill file exceeds the editable size limit")
        return _rebuild(
            archive,
            files,
            skill_package_directories(archive),
            {archive_path: replacement},
            set(),
            max_package_bytes,
        )


def create_skill_package_directory(
    content: bytes, relative_path: str, max_package_bytes: int
) -> bytes:
    archive, files, root = open_skill_package_archive(content, max_package_bytes)
    with archive:
        requested = normalize_skill_package_path(relative_path)
        archive_path = join_skill_package_root(root, requested)
        directories = skill_package_directories(archive)
        if archive_path in files or archive_path in directories:
            raise AppError(
                "SKILL_ENTRY_EXISTS", "Skill entry already exists", status.HTTP_409_CONFLICT
            )
        return _rebuild(archive, files, directories | {archive_path}, {}, set(), max_package_bytes)


def _delete_entry(content: bytes, requested: str, max_package_bytes: int) -> bytes:
    archive, files, root = open_skill_package_archive(content, max_package_bytes)
    with archive:
        directories = skill_package_directories(archive)
        archive_path = resolve_existing_skill_package_path(
            root,
            requested,
            set(files).union(directories),
            include_descendants=True,
        )
        prefix = f"{archive_path}/"
        deleted = {
            path
            for path in (*files, *directories)
            if path == archive_path or path.startswith(prefix)
        }
        if not deleted:
            raise AppError("RESOURCE_NOT_FOUND", "Skill entry not found", status.HTTP_404_NOT_FOUND)
        return _rebuild(archive, files, directories, {}, deleted, max_package_bytes)


def _rebuild(
    archive: zipfile.ZipFile,
    files: dict[str, zipfile.ZipInfo],
    directories: set[str],
    replacements: dict[str, bytes],
    deleted: set[str],
    max_package_bytes: int,
) -> bytes:
    rebuilt = io.BytesIO()
    with zipfile.ZipFile(rebuilt, "w", compression=zipfile.ZIP_DEFLATED) as updated:
        for directory in sorted(directories - deleted):
            updated.writestr(f"{directory}/", b"")
        for path, member in sorted(files.items()):
            if path not in deleted:
                updated.writestr(path, replacements.get(path, archive.read(member)))
        for path, value in sorted(replacements.items()):
            if path not in files:
                updated.writestr(path, value)
    return _validated_rebuild(rebuilt.getvalue(), max_package_bytes)


def _validated_rebuild(content: bytes, max_package_bytes: int) -> bytes:
    package = inspect_skill_package("skill.zip", content, max_package_bytes)
    if package.size_bytes > max_package_bytes:
        raise skill_package_validation_error("Skill ZIP exceeds the configured size limit")
    return content


def _is_utf8_text(content: bytes, size_bytes: int) -> bool:
    if size_bytes > MAX_SKILL_TEXT_FILE_BYTES or b"\x00" in content:
        return False
    try:
        content.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True
