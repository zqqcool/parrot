from __future__ import annotations

import asyncio
import shutil
import subprocess
import zipfile
from pathlib import Path

from app.core.config import SkillBuildSection, SkillSandboxSection
from app.core.errors import AppError
from app.modules.skills.manifest import SkillExecutionSpec
from app.modules.skills.packages import extract_skill_package


def validate_build_inputs(root: Path, spec: SkillExecutionSpec) -> None:
    if any((root / directory).exists() for directory in (".parrot", "node_modules")):
        raise AppError(
            "SKILL_BUILD_INPUT_INVALID",
            "Skill dependency directories must be produced only by the controlled build",
            422,
        )
    if spec.runtime_type == "python":
        _validate_python_lockfiles(root)
    if spec.runtime_type == "node":
        _required_file(root, "package.json")
        _required_file(root, "package-lock.json")
    if spec.runtime_type == "shell" and any(
        (root / name).exists()
        for name in ("requirements.lock", "package.json", "package-lock.json")
    ):
        raise AppError(
            "SKILL_BUILD_INPUT_INVALID", "Shell Skills cannot declare third-party dependencies", 422
        )


async def build_runtime_artifact(
    content: bytes,
    root: Path,
    spec: SkillExecutionSpec,
    sandbox: SkillSandboxSection,
    build: SkillBuildSection,
    max_package_bytes: int,
    max_artifact_bytes: int,
) -> bytes:
    await asyncio.to_thread(extract_skill_package, content, root, max_package_bytes)
    validate_build_inputs(root, spec)
    use_bwrap = shutil.which(sandbox.bwrap_path) is not None
    if sandbox.require_bubblewrap and not use_bwrap:
        raise AppError(
            "SKILL_SANDBOX_UNAVAILABLE", "Required Skill build sandbox is unavailable", 503
        )
    command_root = Path("/build/source") if use_bwrap else root
    if spec.runtime_type == "python" and (root / "requirements.lock").is_file():
        (root / ".parrot" / "python").mkdir(mode=0o700, parents=True, exist_ok=True)
        await _run(
            _python_command(command_root, sandbox, build),
            root,
            build.timeout_seconds,
            sandbox,
            use_bwrap,
        )
    elif spec.runtime_type == "node":
        await _run(
            _node_command(command_root, sandbox, build),
            root,
            build.timeout_seconds,
            sandbox,
            use_bwrap,
        )
    artifact = await asyncio.to_thread(_archive, root)
    if len(artifact) > max_artifact_bytes:
        raise AppError(
            "SKILL_ARTIFACT_TOO_LARGE", "Skill runtime artifact exceeds the allowed size", 422
        )
    return artifact


def _validate_python_lockfiles(root: Path) -> None:
    unsupported = ("requirements.txt", "pyproject.toml", "Pipfile", "poetry.lock")
    if any((root / filename).is_file() for filename in unsupported):
        raise AppError(
            "SKILL_BUILD_INPUT_INVALID",
            "Python Skills may declare dependencies only in requirements.lock",
            422,
        )
    lockfile = root / "requirements.lock"
    if lockfile.is_file():
        _validate_hashed_requirements(lockfile)


def _validate_hashed_requirements(lockfile: Path) -> None:
    for raw_line in lockfile.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("--"):
            continue
        if "--hash=sha256:" not in line:
            raise AppError(
                "SKILL_BUILD_INPUT_INVALID",
                "requirements.lock must pin every dependency with a SHA-256 hash",
                422,
            )


def _required_file(root: Path, name: str) -> None:
    if not (root / name).is_file():
        raise AppError("SKILL_BUILD_INPUT_MISSING", f"Skill build requires {name}", 422)


def _python_command(
    root: Path, sandbox: SkillSandboxSection, build: SkillBuildSection
) -> list[str]:
    target = root / ".parrot" / "python"
    command = [
        sandbox.python_executable,
        "-m",
        "pip",
        "install",
        "--require-hashes",
        "--no-deps",
        "--target",
        str(target),
        "-r",
        str(root / "requirements.lock"),
    ]
    if build.pip_index_url:
        command.extend(("--index-url", build.pip_index_url))
    return command


def _node_command(root: Path, sandbox: SkillSandboxSection, build: SkillBuildSection) -> list[str]:
    command = [sandbox.npm_executable, "ci", "--ignore-scripts", "--omit=dev"]
    if build.npm_registry:
        command.append(f"--registry={build.npm_registry}")
    return command


async def _run(
    command: list[str],
    root: Path,
    timeout_seconds: int,
    sandbox: SkillSandboxSection,
    use_bwrap: bool,
) -> None:
    environment = {
        "HOME": str(root / ".parrot" / "build-home"),
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "PIP_NO_INPUT": "1",
        "NPM_CONFIG_IGNORE_SCRIPTS": "true",
    }
    Path(environment["HOME"]).mkdir(mode=0o700, parents=True, exist_ok=True)
    final_command = (
        _bubblewrap_build_command(command, root, environment, sandbox) if use_bwrap else command
    )
    try:
        completed = await asyncio.to_thread(
            subprocess.run,
            final_command,
            cwd=root,
            env=environment,
            capture_output=True,
            check=False,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise AppError("SKILL_BUILD_FAILED", "Skill dependency build failed", 422) from error
    if completed.returncode:
        raise AppError("SKILL_BUILD_FAILED", "Skill dependency build failed", 422)


def _bubblewrap_build_command(
    command: list[str], root: Path, environment: dict[str, str], sandbox: SkillSandboxSection
) -> list[str]:
    wrapped = [
        sandbox.bwrap_path,
        "--die-with-parent",
        "--new-session",
        "--unshare-user",
        "--unshare-pid",
        "--unshare-ipc",
        "--unshare-uts",
        "--unshare-cgroup",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--tmpfs",
        "/tmp",
    ]
    for path in ("/usr", "/bin", "/lib", "/lib64", "/etc/ssl/certs", "/etc/resolv.conf"):
        if Path(path).exists():
            wrapped.extend(("--ro-bind", path, path))
    wrapped.extend(("--bind", str(root), "/build/source", "--chdir", "/build/source", "--clearenv"))
    for key, value in environment.items():
        translated = value.replace(str(root), "/build/source")
        wrapped.extend(("--setenv", key, translated))
    return [*wrapped, *command]


def _archive(root: Path) -> bytes:
    archive_path = root.parent / "runtime-artifact.zip"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(root.rglob("*")):
            if path.is_file() and not path.is_relative_to(root / ".parrot" / "build-home"):
                archive.write(path, path.relative_to(root).as_posix())
    return archive_path.read_bytes()
