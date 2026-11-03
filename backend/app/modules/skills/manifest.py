from __future__ import annotations

import copy
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from starlette import status

from app.core.errors import AppError

MANIFEST_FILENAME = "manifest.json"
LEGACY_MANIFEST_FILENAMES = frozenset({"skyler.manifest.json", "parrot.manifest.json"})
MANIFEST_IDENTITY_FIELDS = frozenset({"name", "description", "version", "tags", "platforms"})
_RUNTIME_TYPES = frozenset({"python", "node", "shell"})
_TOP_LEVEL_FIELDS = frozenset(
    {"execute", "runtime", "entrypoint", "timeout_seconds", "network_enabled", "env"}
)
_LEGACY_TOP_LEVEL_FIELDS = frozenset(
    {"schema_version", "runtime", "permissions", "input_schema", "output_schema"}
)
_LEGACY_ONLY_TOP_LEVEL_FIELDS = frozenset(
    {"schema_version", "permissions", "input_schema", "output_schema"}
)
_LEGACY_RUNTIME_FIELDS = frozenset({"type", "entrypoint", "timeout_seconds", "env"})
_LEGACY_PERMISSION_FIELDS = frozenset({"network_enabled", "side_effect_level", "risk_level"})
_ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
_RESERVED_ENV_PREFIXES = ("PARROT_", "LD_", "DYLD_", "PYTHON", "NODE_")
_RESERVED_ENV_NAMES = frozenset({"PATH", "HOME", "PWD", "TMPDIR", "BASH_ENV", "ENV", "IFS"})


@dataclass(frozen=True)
class SkillExecutionSpec:
    runtime_type: str
    entrypoint: str
    timeout_seconds: int | None
    env: dict[str, str]
    network_enabled: bool


@dataclass(frozen=True)
class SkillManifest:
    """The sole parser and serializer for the Skill manifest contract."""

    _values: dict[str, object]
    execution_spec: SkillExecutionSpec | None

    @classmethod
    def parse(cls, manifest: Mapping[str, object], *, allow_legacy: bool = True) -> SkillManifest:
        values = _mapping(manifest)
        _reject_identity_fields(values)
        return cls(values, _parse_execution_spec(values, allow_legacy=allow_legacy))

    @classmethod
    def from_json(cls, content: str, *, allow_legacy: bool = False) -> SkillManifest:
        try:
            value = json.loads(content)
        except json.JSONDecodeError as error:
            raise _invalid("Skill manifest must be valid UTF-8 JSON") from error
        if not isinstance(value, dict):
            raise _invalid("Skill manifest must be a JSON object")
        return cls.parse(cast(dict[str, object], value), allow_legacy=allow_legacy)

    @classmethod
    def instruction_only(cls) -> SkillManifest:
        return cls.parse({}, allow_legacy=False)

    def to_mapping(self) -> dict[str, object]:
        return copy.deepcopy(self._values)

    def to_current_mapping(self) -> dict[str, object]:
        """Return the compact current protocol, including when reading a legacy version."""
        spec = self.execution_spec
        if spec is None:
            return {}
        values: dict[str, object] = {
            "execute": True,
            "runtime": spec.runtime_type,
            "entrypoint": spec.entrypoint,
        }
        if spec.timeout_seconds is not None:
            values["timeout_seconds"] = spec.timeout_seconds
        if spec.network_enabled:
            values["network_enabled"] = True
        if spec.env:
            values["env"] = dict(spec.env)
        return values

    def to_current_json(self) -> str:
        values = self.to_current_mapping()
        return f"{json.dumps(values, ensure_ascii=False, indent=2, sort_keys=True)}\n"


def _parse_execution_spec(
    manifest: dict[str, object], *, allow_legacy: bool
) -> SkillExecutionSpec | None:
    """Parse the current execution contract and read historical packages compatibly."""
    if _is_legacy_manifest(manifest):
        if not allow_legacy:
            raise _invalid(
                "Skill manifest uses removed fields; recreate it with the current format"
            )
        return _parse_legacy_manifest(manifest)
    _reject_unknown(manifest, _TOP_LEVEL_FIELDS, "manifest")
    execute = manifest.get("execute", False)
    if not isinstance(execute, bool):
        raise _invalid("Skill manifest execute must be a boolean")
    if not execute:
        if set(manifest) - {"execute"}:
            raise _invalid("Instruction-only Skill manifests may only set execute to false")
        return None
    runtime_type = manifest.get("runtime")
    if runtime_type not in _RUNTIME_TYPES:
        raise _invalid("Skill manifest runtime must be python, node, or shell")
    entrypoint = manifest.get("entrypoint")
    if not isinstance(entrypoint, str) or not entrypoint.strip():
        raise _invalid("Skill manifest entrypoint must be a non-empty string")
    return SkillExecutionSpec(
        runtime_type=cast(str, runtime_type),
        entrypoint=_entrypoint(entrypoint, cast(str, runtime_type)),
        timeout_seconds=_timeout_seconds(manifest.get("timeout_seconds")),
        env=_env(manifest.get("env")),
        network_enabled=_network_enabled(manifest.get("network_enabled")),
    )


def _is_legacy_manifest(manifest: dict[str, object]) -> bool:
    return bool(_LEGACY_ONLY_TOP_LEVEL_FIELDS.intersection(manifest)) or isinstance(
        manifest.get("runtime"), dict
    )


def _parse_legacy_manifest(manifest: dict[str, object]) -> SkillExecutionSpec | None:
    _reject_unknown(manifest, _LEGACY_TOP_LEVEL_FIELDS, "legacy manifest")
    if manifest.get("schema_version", "1.0") != "1.0":
        raise _invalid("Skill manifest schema_version must be exactly '1.0'")
    runtime = _object(manifest.get("runtime"), "runtime")
    permissions = _object(manifest.get("permissions"), "permissions")
    _reject_unknown(permissions, _LEGACY_PERMISSION_FIELDS, "permissions")
    if not runtime:
        return None
    _reject_unknown(runtime, _LEGACY_RUNTIME_FIELDS, "runtime")
    runtime_type = runtime.get("type")
    entrypoint = runtime.get("entrypoint")
    if runtime_type not in _RUNTIME_TYPES:
        raise _invalid("Skill runtime.type must be python, node, or shell")
    if not isinstance(entrypoint, str) or not entrypoint.strip():
        raise _invalid("Skill runtime.entrypoint must be a non-empty string")
    return SkillExecutionSpec(
        runtime_type=cast(str, runtime_type),
        entrypoint=_entrypoint(entrypoint, cast(str, runtime_type)),
        timeout_seconds=_timeout_seconds(runtime.get("timeout_seconds")),
        env=_env(runtime.get("env")),
        network_enabled=_network_enabled(permissions.get("network_enabled")),
    )


def _entrypoint(value: str, runtime_type: str) -> str:
    path = value.strip()
    if (
        path.startswith("/")
        or "\\" in path
        or any(part in {"", ".", ".."} for part in path.split("/"))
    ):
        raise _invalid("Skill manifest entrypoint must be a safe relative path")
    extensions = {"python": (".py",), "node": (".js", ".mjs", ".cjs"), "shell": (".sh",)}
    if not path.endswith(extensions[runtime_type]):
        raise _invalid(f"Skill {runtime_type} entrypoint has an invalid extension")
    return path


def _timeout_seconds(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 900:
        raise _invalid("Skill manifest timeout_seconds must be between 1 and 900")
    return value


def _network_enabled(value: object) -> bool:
    if value is None:
        return False
    if not isinstance(value, bool):
        raise _invalid("Skill manifest network_enabled must be a boolean")
    return value


def _env(value: object) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise _invalid("Skill manifest env must be an object")
    result: dict[str, str] = {}
    for raw_key, raw_value in cast(dict[object, object], value).items():
        if not isinstance(raw_key, str) or not _ENV_NAME.fullmatch(raw_key):
            raise _invalid("Skill manifest env contains an invalid variable name")
        if raw_key in _RESERVED_ENV_NAMES or raw_key.startswith(_RESERVED_ENV_PREFIXES):
            raise _invalid("Skill manifest env cannot override a reserved variable")
        if not isinstance(raw_value, str) or len(raw_value.encode("utf-8")) > 4096:
            raise _invalid("Skill manifest env values must be strings up to 4096 bytes")
        result[raw_key] = raw_value
    return result


def _object(value: object, field: str) -> dict[str, object]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise _invalid(f"Skill {field} must be an object")
    return cast(dict[str, object], value)


def _mapping(value: Mapping[str, object]) -> dict[str, object]:
    return dict(value)


def _reject_identity_fields(manifest: dict[str, object]) -> None:
    identity_fields = sorted(MANIFEST_IDENTITY_FIELDS.intersection(manifest))
    if identity_fields:
        raise _invalid("Skill manifest must not define Skill identity fields")


def _reject_unknown(value: dict[str, object], allowed: frozenset[str], field: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise _invalid(f"Skill {field} has unsupported fields: {', '.join(unknown)}")


def _invalid(message: str) -> AppError:
    return AppError("SKILL_MANIFEST_INVALID", message, status.HTTP_422_UNPROCESSABLE_CONTENT)
