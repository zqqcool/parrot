from __future__ import annotations

import hashlib
import io
import stat
import zipfile
from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from starlette import status

from app.core.errors import AppError
from app.modules.skills.manifest import (
    LEGACY_MANIFEST_FILENAMES,
    MANIFEST_FILENAME,
    SkillManifest,
)

SKILL_MARKDOWN_FILENAME = "SKILL.md"
MAX_SKILL_FILES = 1_000
MAX_SKILL_MARKDOWN_BYTES = 1024 * 1024
MAX_SKILL_TEXT_FILE_BYTES = 1024 * 1024


@dataclass(frozen=True)
class SkillPackage:
    name: str
    description: str
    instructions: str
    manifest: dict[str, object]
    filename: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class SkillPackageFile:
    path: str
    size_bytes: int
    editable: bool
    kind: str = "file"


def inspect_skill_package(
    filename: str,
    content: bytes,
    max_package_bytes: int,
    *,
    allow_legacy_manifest: bool = False,
) -> SkillPackage:
    _validate_package_input(filename, content, max_package_bytes)
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            files = _validated_files(archive, max_package_bytes)
            root = _skill_root(files)
            skill_markdown = _read_text_file(
                archive, files, _join_root(root, SKILL_MARKDOWN_FILENAME)
            )
            name, description = _skill_metadata(skill_markdown)
            manifest = _read_manifest(archive, files, root, allow_legacy_manifest)
            _validate_execution_manifest(manifest, files, root)
    except zipfile.BadZipFile as error:
        raise _validation_error("Skill file must be a valid ZIP archive") from error
    return SkillPackage(
        name=name,
        description=description,
        instructions=skill_markdown,
        manifest=manifest.to_mapping(),
        filename=filename,
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
    )


def list_skill_package_files(content: bytes, max_package_bytes: int) -> list[SkillPackageFile]:
    archive, files, root = _open_skill_archive(content, max_package_bytes)
    with archive:
        entries: list[SkillPackageFile] = []
        for path in sorted(_directory_archive_paths(archive)):
            relative_path = _relative_path(root, path)
            if relative_path:
                entries.append(
                    SkillPackageFile(
                        path=relative_path, size_bytes=0, editable=False, kind="directory"
                    )
                )
        for path, member in sorted(files.items()):
            relative_path = _relative_path(root, path)
            entries.append(
                SkillPackageFile(
                    path=relative_path,
                    size_bytes=member.file_size,
                    editable=_is_utf8_text(archive.read(member), member.file_size),
                    kind="file",
                )
            )
        return entries


def read_skill_package_file(
    content: bytes, relative_path: str, max_package_bytes: int
) -> tuple[str, SkillPackageFile]:
    archive, files, root = _open_skill_archive(content, max_package_bytes)
    with archive:
        requested = _normalize_relative_path(relative_path)
        archive_path = resolve_existing_skill_package_path(root, requested, files)
        member = files.get(archive_path)
        if member is None:
            raise AppError("RESOURCE_NOT_FOUND", "Skill file not found", status.HTTP_404_NOT_FOUND)
        raw_content = archive.read(member)
        if not _is_utf8_text(raw_content, member.file_size):
            raise _validation_error("Skill file is not editable UTF-8 text")
        return raw_content.decode("utf-8"), SkillPackageFile(
            path=requested, size_bytes=member.file_size, editable=True
        )


def extract_skill_package(content: bytes, destination: Path, max_package_bytes: int) -> None:
    archive, files, root = _open_skill_archive(content, max_package_bytes)
    target_root = destination.resolve()
    target_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    with archive:
        for archive_path, member in files.items():
            relative_path = PurePosixPath(_relative_path(root, archive_path))
            target = target_root.joinpath(*relative_path.parts).resolve()
            if not target.is_relative_to(target_root):
                raise _validation_error("Skill ZIP contains an unsafe file path")
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            target.write_bytes(archive.read(member))
            target.chmod(0o600)


def _validate_package_input(filename: str, content: bytes, max_package_bytes: int) -> None:
    if not filename.lower().endswith(".zip"):
        raise _validation_error("Skill file must be a ZIP archive")
    if not content:
        raise _validation_error("Skill ZIP cannot be empty")
    if len(content) > max_package_bytes:
        raise _validation_error("Skill ZIP exceeds the configured size limit")


def _validated_files(
    archive: zipfile.ZipFile, max_package_bytes: int
) -> dict[str, zipfile.ZipInfo]:
    members = archive.infolist()
    if not members:
        raise _validation_error("Skill ZIP cannot be empty")
    if len(members) > MAX_SKILL_FILES:
        raise _validation_error("Skill ZIP contains too many files")
    if sum(member.file_size for member in members) > max_package_bytes:
        raise _validation_error("Skill ZIP uncompressed content exceeds the configured size limit")
    files: dict[str, zipfile.ZipInfo] = {}
    for member in members:
        path = _safe_member_path(member)
        if member.is_dir():
            continue
        if path in files:
            raise _validation_error("Skill ZIP contains duplicate file paths")
        files[path] = member
    return files


def _open_skill_archive(
    content: bytes, max_package_bytes: int
) -> tuple[zipfile.ZipFile, dict[str, zipfile.ZipInfo], str]:
    _validate_package_input("skill.zip", content, max_package_bytes)
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as error:
        raise _validation_error("Skill file must be a valid ZIP archive") from error
    try:
        files = _validated_files(archive, max_package_bytes)
        root = _skill_root(files)
    except Exception:
        archive.close()
        raise
    return archive, files, root


def _safe_member_path(member: zipfile.ZipInfo) -> str:
    raw_path = member.filename
    path = PurePosixPath(raw_path)
    mode = member.external_attr >> 16
    if (
        not raw_path
        or "\\" in raw_path
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
        or (mode and stat.S_ISLNK(mode))
        or member.flag_bits & 0x1
    ):
        raise _validation_error("Skill ZIP contains an unsafe file path")
    return path.as_posix()


def _skill_root(files: dict[str, zipfile.ZipInfo]) -> str:
    if SKILL_MARKDOWN_FILENAME in files:
        return ""
    relevant = [path for path in files if not path.startswith("__MACOSX/")]
    top_levels = {PurePosixPath(path).parts[0] for path in relevant}
    if len(top_levels) == 1:
        root = next(iter(top_levels))
        if _join_root(root, SKILL_MARKDOWN_FILENAME) in files:
            return root
    raise _validation_error("Skill ZIP must contain SKILL.md at its root")


def _join_root(root: str, filename: str) -> str:
    return f"{root}/{filename}" if root else filename


def _relative_path(root: str, path: str) -> str:
    """Hide the Skill root only for entries that are actually beneath it."""
    if root and path == root:
        return ""
    if not root or not path.startswith(f"{root}/"):
        return path
    return path[len(root) + 1 :]


def _directory_archive_paths(archive: zipfile.ZipFile) -> set[str]:
    return {_safe_member_path(member) for member in archive.infolist() if member.is_dir()}


def _normalize_relative_path(value: str) -> str:
    path = PurePosixPath(value.strip().lstrip("/"))
    if (
        not value
        or "\\" in value
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise _validation_error("Skill file path is invalid")
    return path.as_posix()


def open_skill_package_archive(
    content: bytes, max_package_bytes: int
) -> tuple[zipfile.ZipFile, dict[str, zipfile.ZipInfo], str]:
    return _open_skill_archive(content, max_package_bytes)


def skill_package_directories(archive: zipfile.ZipFile) -> set[str]:
    return _directory_archive_paths(archive)


def normalize_skill_package_path(value: str) -> str:
    return _normalize_relative_path(value)


def join_skill_package_root(root: str, path: str) -> str:
    return _join_root(root, path)


def resolve_existing_skill_package_path(
    root: str,
    relative_path: str,
    paths: Collection[str],
    *,
    include_descendants: bool = False,
) -> str:
    """Map an editor path back to an archive entry without corrupting sidecar paths."""
    requested = _normalize_relative_path(relative_path)
    rooted_path = _join_root(root, requested)
    for candidate in dict.fromkeys((rooted_path, requested)):
        if candidate in paths:
            return candidate
        if include_descendants and any(path.startswith(f"{candidate}/") for path in paths):
            return candidate
    return rooted_path


def skill_package_validation_error(message: str) -> AppError:
    return _validation_error(message)


def _is_utf8_text(content: bytes, size_bytes: int) -> bool:
    if size_bytes > MAX_SKILL_TEXT_FILE_BYTES or b"\x00" in content:
        return False
    try:
        content.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def _read_text_file(archive: zipfile.ZipFile, files: dict[str, zipfile.ZipInfo], path: str) -> str:
    member = files.get(path)
    if member is None:
        raise _validation_error("Skill ZIP must contain SKILL.md at its root")
    if member.file_size > MAX_SKILL_MARKDOWN_BYTES:
        raise _validation_error("SKILL.md is too large")
    try:
        return archive.read(member).decode("utf-8")
    except UnicodeDecodeError as error:
        raise _validation_error("SKILL.md must be UTF-8 text") from error


def _skill_metadata(skill_markdown: str) -> tuple[str, str]:
    lines = skill_markdown.splitlines()
    if not lines or lines[0].strip() != "---":
        raise _validation_error("SKILL.md must start with name and description frontmatter")
    values: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        if key.strip() in {"name", "description"}:
            values[key.strip()] = value.strip().strip("\"'").strip()
    name = values.get("name", "")
    description = values.get("description", "")
    if not name or not description:
        raise _validation_error("SKILL.md frontmatter must include name and description")
    if len(name) > 128 or len(description) > 2_000:
        raise _validation_error("SKILL.md metadata exceeds the supported length")
    return name, description


def _read_manifest(
    archive: zipfile.ZipFile,
    files: dict[str, zipfile.ZipInfo],
    root: str,
    allow_legacy_manifest: bool,
) -> SkillManifest:
    legacy = sorted(
        filename for filename in LEGACY_MANIFEST_FILENAMES if _join_root(root, filename) in files
    )
    if legacy:
        raise _validation_error(
            "Skill package must use manifest.json; legacy manifest names are unsupported"
        )
    manifest_path = _join_root(root, MANIFEST_FILENAME)
    member = files.get(manifest_path)
    if member is None:
        return SkillManifest.instruction_only()
    try:
        content = archive.read(member).decode("utf-8")
    except UnicodeDecodeError as error:
        raise _validation_error("Skill manifest must be valid UTF-8 JSON") from error
    return SkillManifest.from_json(content, allow_legacy=allow_legacy_manifest)


def _validate_execution_manifest(
    manifest: SkillManifest, files: dict[str, zipfile.ZipInfo], root: str
) -> None:
    spec = manifest.execution_spec
    if spec is None:
        return
    if _join_root(root, spec.entrypoint) not in files:
        raise _validation_error("Skill execution entrypoint is missing from the package")


def _validation_error(message: str) -> AppError:
    return AppError("SKILL_PACKAGE_INVALID", message, status.HTTP_422_UNPROCESSABLE_CONTENT)
