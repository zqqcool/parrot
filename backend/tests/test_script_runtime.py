import sys
from pathlib import Path

import pytest

from app.core.config import SkillSandboxSection
from app.modules.agent_runtime.script_runtime import SandboxedScriptRuntime


@pytest.mark.asyncio
async def test_script_runtime_is_disabled_without_explicit_runtime_enablement(
    tmp_path: Path,
) -> None:
    runtime = SandboxedScriptRuntime(
        SkillSandboxSection(session_directory=tmp_path),
        enabled=False,
        default_timeout_seconds=30,
        max_timeout_seconds=120,
    )

    result = await runtime.handle({"language": "python", "code": "print('hello')"})

    assert result["code"] == "SCRIPT_EXECUTION_DISABLED"


@pytest.mark.asyncio
async def test_script_runtime_executes_only_with_an_explicit_sandbox_policy(tmp_path: Path) -> None:
    runtime = SandboxedScriptRuntime(
        SkillSandboxSection(
            enabled=True,
            session_directory=tmp_path,
            python_executable=sys.executable,
            require_bubblewrap=False,
            allow_unsafe_local_execution=True,
        ),
        enabled=True,
        default_timeout_seconds=30,
        max_timeout_seconds=120,
    )

    result = await runtime.handle({"language": "python", "code": "print('hello')"})

    assert result["status"] == "succeeded"
    assert result["result"] == {"stdout": "hello\n"}
