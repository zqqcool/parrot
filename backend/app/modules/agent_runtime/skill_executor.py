from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.core.agent_runtime import RuntimeSkillProfile
from app.core.config import SkillSandboxSection
from app.modules.skills.manifest import SkillExecutionSpec, SkillManifest
from app.modules.skills.packages import (
    SkillPackage,
    extract_skill_package,
    inspect_skill_package,
)


@dataclass(frozen=True)
class SkillExecutionContext:
    tenant_id: str
    interaction_id: str
    actor_type: str
    actor_id: str
    request_id: str


@dataclass(frozen=True)
class LoadedSkillPackage:
    package: SkillPackage
    content: bytes


class SkillPackageStorage(Protocol):
    async def read(self, package_path: str) -> bytes: ...


class SkillExecutor(Protocol):
    async def execute(
        self,
        skill: RuntimeSkillProfile,
        context: SkillExecutionContext,
        input_payload: dict[str, object],
    ) -> dict[str, object]: ...


class SandboxedSkillExecutor:
    """Executes validated Python Skill packages outside the application process."""

    def __init__(
        self,
        storage: SkillPackageStorage,
        sandbox: SkillSandboxSection,
        max_package_bytes: int,
    ) -> None:
        self._storage = storage
        self._sandbox = sandbox
        self._max_package_bytes = max_package_bytes

    async def execute(
        self,
        skill: RuntimeSkillProfile,
        context: SkillExecutionContext,
        input_payload: dict[str, object],
    ) -> dict[str, object]:
        disabled = self._disabled_result()
        if disabled is not None:
            return disabled
        if not skill.package_path:
            return _rejected("SKILL_PACKAGE_NOT_AVAILABLE", "The Skill package is unavailable")
        loaded = await self._load_package(skill)
        if isinstance(loaded, dict):
            return loaded
        spec = SkillManifest.parse(loaded.package.manifest).execution_spec
        if spec is None:
            return _rejected(
                "SKILL_ENTRYPOINT_NOT_CONFIGURED", "The Skill has no executable entrypoint"
            )
        timeout_seconds = min(
            spec.timeout_seconds or self._sandbox.default_timeout_seconds,
            self._sandbox.max_timeout_seconds,
        )
        return await self._execute_package(
            loaded.content, spec, timeout_seconds, context, input_payload
        )

    def _disabled_result(self) -> dict[str, object] | None:
        if not self._sandbox.enabled:
            return _rejected(
                "SKILL_EXECUTION_DISABLED", "Skill execution is disabled by configuration"
            )
        bwrap_available = shutil.which(self._sandbox.bwrap_path) is not None
        if self._sandbox.require_bubblewrap and not bwrap_available:
            return _rejected("SKILL_SANDBOX_UNAVAILABLE", "Required Skill sandbox is unavailable")
        if not bwrap_available and not self._sandbox.allow_unsafe_local_execution:
            return _rejected("SKILL_SANDBOX_UNAVAILABLE", "Required Skill sandbox is unavailable")
        return None

    async def _load_package(
        self, skill: RuntimeSkillProfile
    ) -> LoadedSkillPackage | dict[str, object]:
        try:
            content = await self._storage.read(skill.package_path or "")
            package = await asyncio.to_thread(
                inspect_skill_package,
                skill.package_path or "skill.zip",
                content,
                self._max_package_bytes,
                allow_legacy_manifest=True,
            )
        except Exception:
            return _rejected("SKILL_PACKAGE_INVALID", "The Skill package cannot be validated")
        if skill.package_sha256 and package.sha256 != skill.package_sha256:
            return _rejected("SKILL_PACKAGE_CHANGED", "The Skill package integrity check failed")
        return LoadedSkillPackage(package=package, content=content)

    async def _execute_package(
        self,
        content: bytes,
        spec: SkillExecutionSpec,
        timeout_seconds: int,
        context: SkillExecutionContext,
        input_payload: dict[str, object],
    ) -> dict[str, object]:
        started = time.monotonic()
        self._sandbox.session_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._sandbox.session_directory.chmod(0o700)
        with tempfile.TemporaryDirectory(
            prefix="skill-", dir=self._sandbox.session_directory
        ) as raw_session:
            session = Path(raw_session)
            skill_path = session / "skill"
            work_path = session / "work"
            output_path = session / "output.json"
            input_path = session / "input.json"
            work_path.mkdir(mode=0o700)
            input_path.write_text(
                json.dumps(_input_document(context, input_payload), ensure_ascii=False),
                encoding="utf-8",
            )
            try:
                await asyncio.to_thread(
                    extract_skill_package,
                    content,
                    skill_path,
                    self._max_package_bytes,
                )
            except Exception:
                return _rejected("SKILL_PACKAGE_INVALID", "The Skill package cannot be extracted")
            return await self._run_process(
                session,
                skill_path,
                work_path,
                input_path,
                output_path,
                spec,
                timeout_seconds,
                started,
            )

    async def _run_process(
        self,
        session: Path,
        skill_path: Path,
        work_path: Path,
        input_path: Path,
        output_path: Path,
        spec: SkillExecutionSpec,
        timeout_seconds: int,
        started: float,
    ) -> dict[str, object]:
        use_bwrap = shutil.which(self._sandbox.bwrap_path) is not None
        command, cwd, environment = self._command(
            session,
            skill_path,
            work_path,
            input_path,
            output_path,
            spec,
            use_bwrap,
        )
        process: asyncio.subprocess.Process | None = None
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=cwd,
                env=environment,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
            )
            stdout, _stderr = await asyncio.wait_for(process.communicate(), timeout_seconds)
        except TimeoutError:
            await _stop_process(process)
            return _rejected("SKILL_EXECUTION_TIMEOUT", "The Skill execution timed out")
        except asyncio.CancelledError:
            await _stop_process(process)
            raise
        except OSError:
            return _rejected("SKILL_EXECUTION_FAILED", "The Skill process could not be started")
        duration_ms = int((time.monotonic() - started) * 1000)
        if process.returncode != 0:
            return _failed("SKILL_EXECUTION_FAILED", duration_ms)
        return _success(
            output_path,
            stdout,
            duration_ms,
            self._sandbox.max_output_bytes,
        )

    def _command(
        self,
        session: Path,
        skill_path: Path,
        work_path: Path,
        input_path: Path,
        output_path: Path,
        spec: SkillExecutionSpec,
        use_bwrap: bool,
    ) -> tuple[list[str], str, dict[str, str]]:
        environment = {
            "HOME": str(work_path),
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "PARROT_SKILL_INPUT_JSON": str(input_path),
            "PARROT_SKILL_OUTPUT_JSON": str(output_path),
            "PARROT_SKILL_WORK_DIR": str(work_path),
            "PARROT_SKILL_SESSION_DIR": str(session),
            **spec.env,
        }
        if spec.runtime_type == "python":
            environment["PYTHONPATH"] = str(skill_path / ".parrot" / "python")
        command = _runtime_command(self._sandbox, spec.runtime_type, skill_path / spec.entrypoint)
        if not use_bwrap:
            return command, str(work_path), environment
        return self._bubblewrap_command(session, skill_path, spec), "/", {}

    def _bubblewrap_command(
        self, session: Path, skill_path: Path, spec: SkillExecutionSpec
    ) -> list[str]:
        command = [
            self._sandbox.bwrap_path,
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
        for path in ("/usr", "/bin", "/lib", "/lib64", "/etc/ssl/certs"):
            if Path(path).exists():
                command.extend(("--ro-bind", path, path))
        command.extend(
            (
                "--ro-bind",
                str(skill_path),
                "/skill",
                "--bind",
                str(session),
                "/session",
                "--chdir",
                "/session/work",
                "--clearenv",
                "--setenv",
                "HOME",
                "/session/work",
                "--setenv",
                "PATH",
                "/usr/local/bin:/usr/bin:/bin",
                "--setenv",
                "PARROT_SKILL_INPUT_JSON",
                "/session/input.json",
                "--setenv",
                "PARROT_SKILL_OUTPUT_JSON",
                "/session/output.json",
                "--setenv",
                "PARROT_SKILL_WORK_DIR",
                "/session/work",
                "--setenv",
                "PARROT_SKILL_SESSION_DIR",
                "/session",
            )
        )
        if not spec.network_enabled:
            command.append("--unshare-net")
        elif Path("/etc/resolv.conf").exists():
            command.extend(("--ro-bind", "/etc/resolv.conf", "/etc/resolv.conf"))
        for key, value in spec.env.items():
            command.extend(("--setenv", key, value))
        if spec.runtime_type == "python":
            command.extend(("--setenv", "PYTHONPATH", "/skill/.parrot/python"))
        command.extend(
            _runtime_command(self._sandbox, spec.runtime_type, Path(f"/skill/{spec.entrypoint}"))
        )
        return command


def _input_document(
    context: SkillExecutionContext, input_payload: dict[str, object]
) -> dict[str, object]:
    return {
        "input": input_payload,
        "interaction": {
            "tenant_id": context.tenant_id,
            "interaction_id": context.interaction_id,
            "actor_type": context.actor_type,
            "actor_id": context.actor_id,
            "request_id": context.request_id,
        },
    }


async def _stop_process(process: asyncio.subprocess.Process | None) -> None:
    if process is None or process.returncode is not None:
        return
    process.terminate()
    try:
        await asyncio.wait_for(process.wait(), timeout=2)
    except TimeoutError:
        process.kill()
        await process.wait()


def _success(
    output_path: Path,
    stdout: bytes,
    duration_ms: int,
    max_output_bytes: int,
) -> dict[str, object]:
    if output_path.exists():
        try:
            raw = output_path.read_bytes()
            if len(raw) > max_output_bytes:
                return _rejected(
                    "SKILL_OUTPUT_TOO_LARGE", "The Skill output exceeds the allowed size"
                )
            value = json.loads(raw)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return _rejected("SKILL_OUTPUT_INVALID", "The Skill output is not valid JSON")
        if not isinstance(value, dict):
            return _rejected("SKILL_OUTPUT_INVALID", "The Skill output must be a JSON object")
        return {"status": "succeeded", "duration_ms": duration_ms, "result": value}
    return {
        "status": "succeeded",
        "duration_ms": duration_ms,
        "result": {"stdout": stdout.decode("utf-8", errors="replace")[-4_000:]},
    }


def _failed(code: str, duration_ms: int) -> dict[str, object]:
    return {
        "status": "failed",
        "code": code,
        "duration_ms": duration_ms,
    }


def _rejected(code: str, message: str) -> dict[str, object]:
    return {"status": "rejected", "code": code, "message": message}


def _runtime_command(
    sandbox: SkillSandboxSection, runtime_type: str, entrypoint: Path
) -> list[str]:
    if runtime_type == "python":
        return [sandbox.python_executable, str(entrypoint)]
    if runtime_type == "node":
        return [sandbox.node_executable, str(entrypoint)]
    return [sandbox.shell_executable, str(entrypoint)]
