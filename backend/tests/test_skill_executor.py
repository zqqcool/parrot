import hashlib
import io
import sys
import zipfile
from pathlib import Path

import pytest

from app.core.agent_runtime import RuntimeSkillProfile
from app.core.config import SkillSandboxSection
from app.core.errors import AppError
from app.modules.agent_runtime.skill_executor import (
    SandboxedSkillExecutor,
    SkillExecutionContext,
)
from app.modules.skills.packages import inspect_skill_package


class Storage:
    def __init__(self, content: bytes) -> None:
        self.content = content

    async def read(self, package_path: str) -> bytes:
        assert package_path == "tenant_test/skill/v1.zip"
        return self.content


def context() -> SkillExecutionContext:
    return SkillExecutionContext(
        tenant_id="tenant_test",
        interaction_id="interaction_test",
        actor_type="user",
        actor_id="user_test",
        request_id="request_test",
    )


def sandbox(tmp_path: Path, *, enabled: bool = True) -> SkillSandboxSection:
    return SkillSandboxSection(
        enabled=enabled,
        session_directory=tmp_path / "sessions",
        python_executable=sys.executable,
        bwrap_path="missing-bwrap",
        require_bubblewrap=False,
        allow_unsafe_local_execution=True,
        default_timeout_seconds=10,
        max_timeout_seconds=10,
        max_output_bytes=4_096,
    )


@pytest.mark.asyncio
async def test_skill_executor_runs_validated_package_with_explicit_local_override(
    tmp_path: Path,
) -> None:
    content = _zip(
        {
            "SKILL.md": "---\nname: echo\ndescription: Echo a provided value\n---\n",
            "manifest.json": '{"execute":true,"runtime":"python","entrypoint":"scripts/main.py"}',
            "scripts/main.py": (
                "import json\n"
                "import os\n"
                "with open(os.environ['PARROT_SKILL_INPUT_JSON'], encoding='utf-8') as source:\n"
                "    value = json.load(source)\n"
                "output_path = os.environ['PARROT_SKILL_OUTPUT_JSON']\n"
                "result = {'echo': value['input']['value'], "
                "'tenant': value['interaction']['tenant_id']}\n"
                "with open(output_path, 'w', encoding='utf-8') as target:\n"
                "    json.dump(result, target)\n"
            ),
        }
    )
    package = inspect_skill_package("echo.zip", content, 50 * 1024 * 1024)
    skill = RuntimeSkillProfile(
        id="skill_test",
        name="echo",
        description="Echo a provided value",
        instructions=package.instructions,
        manifest=package.manifest,
        version=1,
        package_path="tenant_test/skill/v1.zip",
        package_sha256=hashlib.sha256(content).hexdigest(),
    )

    result = await SandboxedSkillExecutor(
        Storage(content), sandbox(tmp_path), 50 * 1024 * 1024
    ).execute(skill, context(), {"value": "hello"})

    assert result["status"] == "succeeded"
    assert result["result"] == {"echo": "hello", "tenant": "tenant_test"}
    assert list((tmp_path / "sessions").iterdir()) == []


@pytest.mark.asyncio
async def test_skill_executor_fails_closed_when_execution_is_disabled(tmp_path: Path) -> None:
    skill = RuntimeSkillProfile(
        id="skill_test",
        name="echo",
        description="Echo",
        instructions="",
        manifest={"execute": True, "runtime": "python", "entrypoint": "scripts/main.py"},
        version=1,
        package_path="tenant_test/skill/v1.zip",
    )

    result = await SandboxedSkillExecutor(
        Storage(b""), sandbox(tmp_path, enabled=False), 1024
    ).execute(skill, context(), {})

    assert result["code"] == "SKILL_EXECUTION_DISABLED"


@pytest.mark.asyncio
async def test_skill_executor_returns_stdout_when_no_json_output_is_written(
    tmp_path: Path,
) -> None:
    content = _zip(
        {
            "SKILL.md": "---\nname: silent\ndescription: Silent Skill\n---\n",
            "manifest.json": '{"execute":true,"runtime":"python","entrypoint":"main.py"}',
            "main.py": "print('not-json-output')\n",
        }
    )
    package = inspect_skill_package("silent.zip", content, 50 * 1024 * 1024)
    skill = RuntimeSkillProfile(
        id="skill_test",
        name="silent",
        description="Silent Skill",
        instructions=package.instructions,
        manifest=package.manifest,
        version=1,
        package_path="tenant_test/skill/v1.zip",
        package_sha256=hashlib.sha256(content).hexdigest(),
    )

    result = await SandboxedSkillExecutor(
        Storage(content), sandbox(tmp_path), 50 * 1024 * 1024
    ).execute(skill, context(), {})

    assert result["status"] == "succeeded"
    assert result["result"] == {"stdout": "not-json-output\n"}


def test_skill_package_rejects_an_executable_manifest_without_the_declared_file() -> None:
    content = _zip(
        {
            "SKILL.md": "---\nname: invalid\ndescription: Invalid Skill\n---\n",
            "manifest.json": (
                '{"execute":true,"runtime":"python","entrypoint":"scripts/missing.py"}'
            ),
        }
    )

    with pytest.raises(AppError, match="entrypoint"):
        inspect_skill_package("invalid.zip", content, 50 * 1024 * 1024)


def _zip(entries: dict[str, str]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for path, value in entries.items():
            archive.writestr(path, value)
    return output.getvalue()
