from pathlib import Path

import pytest

from app.core.errors import AppError
from app.modules.skills.build_artifact import validate_build_inputs
from app.modules.skills.manifest import SkillManifest


@pytest.mark.parametrize(
    ("runtime_type", "entrypoint"),
    (("python", "scripts/main.py"), ("node", "scripts/main.mjs"), ("shell", "scripts/main.sh")),
)
def test_manifest_accepts_the_supported_fixed_entrypoints(
    runtime_type: str, entrypoint: str
) -> None:
    spec = SkillManifest.parse(
        {
            "execute": True,
            "runtime": runtime_type,
            "entrypoint": entrypoint,
            "network_enabled": False,
        }
    ).execution_spec

    assert spec is not None
    assert spec.runtime_type == runtime_type
    assert spec.network_enabled is False


def test_manifest_rejects_reserved_environment_and_retired_fields() -> None:
    with pytest.raises(AppError, match="reserved"):
        SkillManifest.parse(
            {
                "execute": True,
                "runtime": "python",
                "entrypoint": "scripts/main.py",
                "env": {"PATH": "/unsafe"},
            }
        )
    with pytest.raises(AppError, match="removed"):
        SkillManifest.parse({"input_schema": {"type": "object"}}, allow_legacy=False)


def test_manifest_defaults_to_network_isolation_and_instruction_only() -> None:
    assert SkillManifest.parse({}).execution_spec is None
    assert SkillManifest.parse({"execute": False}).execution_spec is None
    spec = SkillManifest.parse(
        {"execute": True, "runtime": "shell", "entrypoint": "run.sh"}
    ).execution_spec
    assert spec is not None
    assert spec.network_enabled is False


def test_manifest_reads_legacy_published_package_only_when_allowed() -> None:
    legacy: dict[str, object] = {"runtime": {"type": "python", "entrypoint": "main.py"}}

    assert SkillManifest.parse(legacy).execution_spec is not None
    with pytest.raises(AppError, match="removed"):
        SkillManifest.parse(legacy, allow_legacy=False)


def test_python_dependencies_must_use_hashed_root_lockfile(tmp_path: Path) -> None:
    spec = SkillManifest.parse(
        {"execute": True, "runtime": "python", "entrypoint": "main.py"}
    ).execution_spec
    assert spec is not None
    (tmp_path / "requirements.txt").write_text("requests\n", encoding="utf-8")
    with pytest.raises(AppError, match="requirements.lock"):
        validate_build_inputs(tmp_path, spec)
    (tmp_path / "requirements.txt").unlink()
    (tmp_path / "requirements.lock").write_text("requests==2.0\n", encoding="utf-8")
    with pytest.raises(AppError, match="SHA-256"):
        validate_build_inputs(tmp_path, spec)
