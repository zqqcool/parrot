import io
import zipfile
from pathlib import Path
from typing import Any, cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.infrastructure.db.session import DatabaseManager
from app.infrastructure.skill_package_storage import LocalSkillPackageStorage
from app.modules.iam.schemas import PrincipalContext
from app.modules.skills.models import Skill
from app.modules.skills.package_mutations import (
    create_skill_package_directory,
    create_skill_package_file,
    delete_skill_package_entry,
    replace_skill_package_file,
)
from app.modules.skills.package_service import normalize_skill_package_import
from app.modules.skills.packages import (
    inspect_skill_package,
    list_skill_package_files,
    read_skill_package_file,
)
from app.modules.skills.service import SkillService


def test_skill_package_reads_frontmatter_manifest_and_nested_root() -> None:
    package = inspect_skill_package(
        "weather.zip",
        _zip(
            {
                "weather/SKILL.md": (
                    "---\nname: weather\ndescription: Look up weather\n---\n\n# Weather\n"
                ),
                "weather/manifest.json": '{"execute": false}',
                "weather/scripts/lookup.py": "print('weather')\n",
            }
        ),
        50 * 1024 * 1024,
    )

    assert package.name == "weather"
    assert package.description == "Look up weather"
    assert package.manifest == {"execute": False}
    assert package.instructions.startswith("---")
    assert len(package.sha256) == 64


@pytest.mark.parametrize("legacy_name", ("skyler.manifest.json", "parrot.manifest.json"))
def test_skill_package_rejects_legacy_manifest_filenames(legacy_name: str) -> None:
    with pytest.raises(AppError, match="manifest.json"):
        inspect_skill_package(
            "weather.zip",
            _zip(
                {
                    "SKILL.md": "---\nname: weather\ndescription: Lookup\n---\n",
                    legacy_name: "{}",
                }
            ),
            50 * 1024 * 1024,
        )


def test_skill_package_rejects_retired_manifest_fields_for_new_imports() -> None:
    with pytest.raises(AppError, match="removed"):
        inspect_skill_package(
            "weather.zip",
            _zip(
                {
                    "SKILL.md": "---\nname: weather\ndescription: Lookup\n---\n",
                    "manifest.json": '{"schema_version": "1.0"}',
                }
            ),
            50 * 1024 * 1024,
        )


def test_skill_package_import_materializes_a_missing_default_manifest() -> None:
    content = _zip(
        {"SKILL.md": "---\nname: weather\ndescription: Look up weather\n---\n# Weather\n"}
    )

    package, normalized_content = normalize_skill_package_import(
        "weather.zip", content, 50 * 1024 * 1024
    )
    manifest, file = read_skill_package_file(normalized_content, "manifest.json", 50 * 1024 * 1024)

    assert normalized_content != content
    assert package.manifest == {}
    assert file.editable is True
    assert manifest == "{}\n"


def test_skill_package_import_preserves_a_valid_manifest() -> None:
    content = _zip(
        {
            "SKILL.md": "---\nname: weather\ndescription: Look up weather\n---\n# Weather\n",
            "manifest.json": '{"execute": false}',
        }
    )

    package, normalized_content = normalize_skill_package_import(
        "weather.zip", content, 50 * 1024 * 1024
    )

    assert normalized_content == content
    assert package.manifest == {"execute": False}


def test_skill_package_import_rejects_an_invalid_existing_manifest() -> None:
    content = _zip(
        {
            "SKILL.md": "---\nname: weather\ndescription: Look up weather\n---\n# Weather\n",
            "manifest.json": '{"schema_version": "1.0"}',
        }
    )

    with pytest.raises(AppError, match="removed"):
        normalize_skill_package_import("weather.zip", content, 50 * 1024 * 1024)


def test_skill_package_file_editor_preserves_tree_and_revalidates_contract() -> None:
    original = _zip(
        {
            "weather/SKILL.md": (
                "---\nname: weather\ndescription: Look up weather\n---\n# Weather\n"
            ),
            "weather/references/usage.md": "Use metric units.\n",
            "weather/scripts/lookup.py": "print('weather')\n",
        }
    )

    files = list_skill_package_files(original, 50 * 1024 * 1024)
    assert [item.path for item in files] == [
        "SKILL.md",
        "references/usage.md",
        "scripts/lookup.py",
    ]

    updated = replace_skill_package_file(
        original,
        "references/usage.md",
        "Use Celsius by default.\n",
        50 * 1024 * 1024,
    )
    value, file = read_skill_package_file(updated, "references/usage.md", 50 * 1024 * 1024)

    assert file.editable is True
    assert value == "Use Celsius by default.\n"
    assert inspect_skill_package("weather.zip", updated, 50 * 1024 * 1024).name == "weather"


def test_skill_package_editor_deletes_macos_sidecar_directories() -> None:
    original = _zip(
        {
            "weather/": "",
            "weather/SKILL.md": (
                "---\nname: weather\ndescription: Look up weather\n---\n# Weather\n"
            ),
            "weather/main.py": "print('weather')\n",
            "__MACOSX/weather/._SKILL.md": "metadata",
            "__MACOSX/weather/._main.py": "metadata",
        }
    )

    files = list_skill_package_files(original, 50 * 1024 * 1024)

    assert [item.path for item in files] == [
        "__MACOSX/weather/._SKILL.md",
        "__MACOSX/weather/._main.py",
        "SKILL.md",
        "main.py",
    ]

    removed = delete_skill_package_entry(original, "__MACOSX", 50 * 1024 * 1024)

    assert [item.path for item in list_skill_package_files(removed, 50 * 1024 * 1024)] == [
        "SKILL.md",
        "main.py",
    ]


def test_manifest_addition_and_edits_use_the_canonical_manifest_document() -> None:
    original = _zip(
        {
            "SKILL.md": "---\nname: weather\ndescription: Look up weather\n---\n# Weather\n",
            "scripts/main.py": "print('weather')\n",
        }
    )

    added = create_skill_package_file(
        original,
        "manifest.json",
        '{"execute":false}',
        50 * 1024 * 1024,
    )
    initial_content, _ = read_skill_package_file(added, "manifest.json", 50 * 1024 * 1024)
    updated = replace_skill_package_file(
        added,
        "manifest.json",
        '{"runtime":"python","execute":true,"entrypoint":"scripts/main.py"}',
        50 * 1024 * 1024,
    )
    content, _ = read_skill_package_file(updated, "manifest.json", 50 * 1024 * 1024)

    assert inspect_skill_package("weather.zip", updated, 50 * 1024 * 1024).manifest == {
        "execute": True,
        "runtime": "python",
        "entrypoint": "scripts/main.py",
    }
    assert initial_content == "{}\n"
    assert content == (
        '{\n  "entrypoint": "scripts/main.py",\n  "execute": true,\n  "runtime": "python"\n}\n'
    )


def test_skill_package_file_editor_rejects_invalid_skill_frontmatter() -> None:
    original = _zip(
        {"SKILL.md": "---\nname: weather\ndescription: Look up weather\n---\n# Weather\n"}
    )

    with pytest.raises(AppError, match="frontmatter"):
        replace_skill_package_file(
            original,
            "SKILL.md",
            "# Invalid\n",
            50 * 1024 * 1024,
        )


def test_skill_package_supports_draft_file_and_directory_operations() -> None:
    original = _zip(
        {"SKILL.md": "---\nname: weather\ndescription: Look up weather\n---\n# Weather\n"}
    )

    with_directory = create_skill_package_directory(original, "references", 50 * 1024 * 1024)
    with_file = create_skill_package_file(
        with_directory,
        "references/usage.md",
        "Use metric units.\n",
        50 * 1024 * 1024,
    )
    entries = list_skill_package_files(with_file, 50 * 1024 * 1024)

    assert [(entry.path, entry.kind) for entry in entries] == [
        ("references", "directory"),
        ("SKILL.md", "file"),
        ("references/usage.md", "file"),
    ]
    removed = delete_skill_package_entry(with_file, "references", 50 * 1024 * 1024)
    assert [entry.path for entry in list_skill_package_files(removed, 50 * 1024 * 1024)] == [
        "SKILL.md"
    ]
    assert inspect_skill_package("weather.zip", removed, 50 * 1024 * 1024).name == "weather"


@pytest.mark.parametrize(
    ("filename", "entries", "expected_message"),
    [
        ("weather.txt", {"SKILL.md": "---\nname: weather\ndescription: Lookup\n---"}, "ZIP"),
        ("weather.zip", {"../SKILL.md": "unsafe"}, "unsafe"),
        ("weather.zip", {"SKILL.md": "# No frontmatter"}, "frontmatter"),
        (
            "weather.zip",
            {
                "SKILL.md": "---\nname: weather\ndescription: Lookup\n---",
                "manifest.json": '{"name": "wrong"}',
            },
            "identity",
        ),
    ],
)
def test_skill_package_rejects_invalid_input(
    filename: str, entries: dict[str, str], expected_message: str
) -> None:
    with pytest.raises(AppError, match=expected_message):
        inspect_skill_package(filename, _zip(entries), 50 * 1024 * 1024)


@pytest.mark.asyncio
async def test_skill_package_import_creates_a_tenant_draft_and_stores_archive(
    tmp_path: Path,
) -> None:
    session = _FakeSession()
    database = _FakeDatabase()
    service = SkillService(
        cast(AsyncSession, session),
        cast(DatabaseManager, database),
        LocalSkillPackageStorage(tmp_path),
        50 * 1024 * 1024,
    )
    content = _zip(
        {"SKILL.md": "---\nname: weather\ndescription: Look up weather\n---\n# Weather\n"}
    )

    result = await service.import_package(_principal(), "tenant_test", "weather.zip", content)

    skill = next(item for item in session.items if isinstance(item, Skill))
    assert result.status == "draft"
    assert result.package_filename == "weather.zip"
    assert skill.package_path is not None
    stored = (tmp_path / skill.package_path).read_bytes()
    assert stored != content
    assert read_skill_package_file(stored, "manifest.json", 50 * 1024 * 1024)[0] == "{}\n"
    assert database.set_tenant_calls == [(session, "tenant_test")]


@pytest.mark.asyncio
async def test_skill_delete_rejects_agent_bound_skill() -> None:
    session = _FakeSession()
    session.add(_skill())
    guard = _SkillDeletionGuard(bound=True)
    service = SkillService(
        cast(AsyncSession, session),
        cast(DatabaseManager, _FakeDatabase()),
        deletion_guard=guard,
    )

    with pytest.raises(AppError) as error:
        await service.delete(_principal(), "tenant_test", "skill_weather")

    assert error.value.code == "SKILL_IN_USE"
    assert error.value.status_code == 409
    assert session.deleted == []
    assert guard.calls == [("tenant_test", "skill_weather")]


@pytest.mark.asyncio
async def test_skill_delete_removes_unbound_skill_and_writes_audit_record() -> None:
    session = _FakeSession()
    skill = _skill()
    session.add(skill)
    service = SkillService(
        cast(AsyncSession, session),
        cast(DatabaseManager, _FakeDatabase()),
        deletion_guard=_SkillDeletionGuard(bound=False),
    )

    await service.delete(_principal(), "tenant_test", skill.id)

    assert session.deleted == [skill]
    assert any(getattr(item, "action", None) == "skill.delete" for item in session.items)


def _skill() -> Skill:
    return Skill(
        id="skill_weather",
        tenant_id="tenant_test",
        name="weather",
        description="Look up weather",
        manifest={},
        instructions="Use metric units.",
    )


def _zip(entries: dict[str, str]) -> bytes:
    content = io.BytesIO()
    with zipfile.ZipFile(content, "w") as archive:
        for path, value in entries.items():
            archive.writestr(path, value)
    return content.getvalue()


def _principal() -> PrincipalContext:
    return PrincipalContext(
        tenant_id="tenant_test",
        subject_id="user_test",
        username="admin",
        display_name="Admin",
        permissions=("skills.manage",),
        tenants=(),
        must_change_password=False,
        request_id="req_test",
    )


class _FakeSession:
    def __init__(self) -> None:
        self.items: list[Any] = []
        self.deleted: list[Any] = []

    async def scalar(self, _statement: object) -> Skill | None:
        return next((item for item in self.items if isinstance(item, Skill)), None)

    def add(self, item: Any) -> None:
        self.items.append(item)

    async def delete(self, item: Any) -> None:
        self.deleted.append(item)

    async def flush(self) -> None:
        for item in self.items:
            if isinstance(item, Skill):
                item.version = 1


class _FakeDatabase:
    def __init__(self) -> None:
        self.set_tenant_calls: list[tuple[_FakeSession, str]] = []

    async def set_tenant(self, session: _FakeSession, tenant_id: str) -> None:
        self.set_tenant_calls.append((session, tenant_id))


class _SkillDeletionGuard:
    def __init__(self, *, bound: bool) -> None:
        self.bound = bound
        self.calls: list[tuple[str, str]] = []

    async def is_bound_to_agent(self, tenant_id: str, skill_id: str) -> bool:
        self.calls.append((tenant_id, skill_id))
        return self.bound
