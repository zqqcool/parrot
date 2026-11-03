from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
import time
from pathlib import Path
from typing import Protocol

from app.core.config import SkillSandboxSection

_MAX_CODE_CHARS = 16_000


class ScriptRuntimePort(Protocol):
    async def handle(self, arguments: dict[str, object]) -> dict[str, object]: ...


class SandboxedScriptRuntime:
    """Runs one short script in the same isolation policy used by executable Skills."""

    def __init__(
        self,
        sandbox: SkillSandboxSection,
        *,
        enabled: bool,
        default_timeout_seconds: int,
        max_timeout_seconds: int,
    ) -> None:
        self._sandbox = sandbox
        self._enabled = enabled
        self._default_timeout_seconds = default_timeout_seconds
        self._max_timeout_seconds = max_timeout_seconds

    async def handle(self, arguments: dict[str, object]) -> dict[str, object]:
        validation = self._validate(arguments)
        if validation is not None:
            return validation
        language = str(arguments["language"])
        code = str(arguments["code"])
        timeout = _timeout(arguments.get("timeout_seconds"), self._default_timeout_seconds)
        timeout = min(timeout, self._max_timeout_seconds)
        try:
            return await self._execute(language, code, timeout, arguments.get("input_payload", {}))
        except OSError:
            return _rejected("SCRIPT_EXECUTION_FAILED", "Script session could not be created")

    def _validate(self, arguments: dict[str, object]) -> dict[str, object] | None:
        if not self._enabled or not self._sandbox.enabled:
            return _rejected("SCRIPT_EXECUTION_DISABLED", "Script execution is disabled")
        if arguments.get("network_access") is True:
            return _rejected("SCRIPT_NETWORK_NOT_AVAILABLE", "Script network access is disabled")
        language = arguments.get("language")
        code = arguments.get("code")
        payload = arguments.get("input_payload", {})
        if language not in {"python", "shell"}:
            return _rejected("SCRIPT_LANGUAGE_INVALID", "language must be python or shell")
        if not isinstance(code, str) or not code.strip() or len(code) > _MAX_CODE_CHARS:
            return _rejected("SCRIPT_CODE_INVALID", "code is empty or exceeds the size limit")
        if not isinstance(payload, dict):
            return _rejected("SCRIPT_INPUT_INVALID", "input_payload must be a JSON object")
        if self._sandbox.require_bubblewrap and not _has_bubblewrap(self._sandbox):
            return _rejected("SCRIPT_SANDBOX_UNAVAILABLE", "Bubblewrap is required")
        if not _has_bubblewrap(self._sandbox) and not self._sandbox.allow_unsafe_local_execution:
            return _rejected("SCRIPT_SANDBOX_UNAVAILABLE", "No safe script sandbox is available")
        return None

    async def _execute(
        self, language: str, code: str, timeout_seconds: int, input_payload: object
    ) -> dict[str, object]:
        root = self._sandbox.session_directory / "scripts"
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        root.chmod(0o700)
        with tempfile.TemporaryDirectory(prefix="script-", dir=root) as raw_session:
            session = Path(raw_session)
            source = session / ("script.py" if language == "python" else "script.sh")
            work = session / "work"
            input_path = session / "input.json"
            work.mkdir(mode=0o700)
            source.write_text(code, encoding="utf-8")
            source.chmod(0o500)
            input_path.write_text(json.dumps(input_payload, ensure_ascii=False), encoding="utf-8")
            started = time.monotonic()
            process: asyncio.subprocess.Process | None = None
            try:
                command, cwd, environment = self._command(session, source, language)
                process = await asyncio.create_subprocess_exec(
                    *command,
                    cwd=cwd,
                    env=environment,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    start_new_session=True,
                )
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout_seconds)
            except TimeoutError:
                await _stop(process)
                return _rejected("SCRIPT_EXECUTION_TIMEOUT", "Script execution timed out")
            except OSError:
                return _rejected("SCRIPT_EXECUTION_FAILED", "Script process could not be started")
            duration_ms = int((time.monotonic() - started) * 1_000)
            if process.returncode != 0:
                return {
                    "status": "failed",
                    "code": "SCRIPT_EXECUTION_FAILED",
                    "duration_ms": duration_ms,
                    "stderr": _excerpt(stderr, self._sandbox.max_output_bytes),
                }
            return {
                "status": "succeeded",
                "duration_ms": duration_ms,
                "result": {"stdout": _excerpt(stdout, self._sandbox.max_output_bytes)},
            }

    def _command(
        self, session: Path, source: Path, language: str
    ) -> tuple[list[str], str, dict[str, str]]:
        command = _interpreter_command(language, source, self._sandbox.python_executable)
        environment = {
            "HOME": str(session / "work"),
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "PARROT_SCRIPT_INPUT_JSON": str(session / "input.json"),
            "PARROT_SCRIPT_WORK_DIR": str(session / "work"),
        }
        if not _has_bubblewrap(self._sandbox):
            return command, str(session / "work"), environment
        return _bubblewrap_command(self._sandbox, session, source, language), "/", {}


def _has_bubblewrap(sandbox: SkillSandboxSection) -> bool:
    return shutil.which(sandbox.bwrap_path) is not None


def _timeout(value: object, default: int) -> int:
    return (
        value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else default
    )


def _interpreter_command(language: str, source: Path, python_executable: str) -> list[str]:
    return [python_executable, str(source)] if language == "python" else ["/bin/sh", str(source)]


def _bubblewrap_command(
    sandbox: SkillSandboxSection, session: Path, source: Path, language: str
) -> list[str]:
    command = [
        sandbox.bwrap_path,
        "--die-with-parent",
        "--new-session",
        "--unshare-all",
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
            "--dir",
            "/script",
            "--ro-bind",
            str(source),
            "/script/source",
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
            "PARROT_SCRIPT_INPUT_JSON",
            "/session/input.json",
            "--setenv",
            "PARROT_SCRIPT_WORK_DIR",
            "/session/work",
        )
    )
    return [
        *command,
        *_interpreter_command(language, Path("/script/source"), sandbox.python_executable),
    ]


async def _stop(process: asyncio.subprocess.Process | None) -> None:
    if process is None or process.returncode is not None:
        return
    process.terminate()
    try:
        await asyncio.wait_for(process.wait(), timeout=2)
    except TimeoutError:
        process.kill()
        await process.wait()


def _excerpt(value: bytes, maximum: int) -> str:
    return value.decode("utf-8", errors="replace")[-maximum:]


def _rejected(code: str, message: str) -> dict[str, object]:
    return {"status": "rejected", "code": code, "message": message}
