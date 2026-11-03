import base64
import re
import secrets
import tomllib
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from app.core.config import BACKEND_ROOT, AppConfig, knowledge_vector_runtime_issue, load_app_config
from app.core.task_dispatch import TaskDispatcher
from app.modules.agent_runtime.durable import DurableInProcessRuntime
from app.modules.interactions.runtime_factory import build_runtime

ROOT = Path(__file__).resolve().parents[1]


def test_dev_config_loads_complete_inline_configuration() -> None:
    settings = load_app_config(ROOT / "config" / "dev.toml")

    assert settings.app.environment == "dev"
    assert settings.api.prefix == "/api/v1"
    assert settings.database.url.startswith("postgresql+asyncpg://parrot_app:")
    assert settings.logging.json_output is False
    assert settings.logging.level == "DEBUG"
    assert settings.ai.debug_log_prompts is False
    assert settings.ai.debug_capture_prompts is False
    assert settings.ai.agent_direct_rendering_enabled is True
    assert settings.ai.knowledge_parallel_evidence_enabled is True
    assert settings.ai.agent_loop_subagents_enabled is True
    assert settings.ai.agent_max_subagent_tasks == 5
    assert settings.ai.agent_max_parallel_subagents == 3
    assert settings.ai.agent_max_supporting_skills == 3
    assert settings.skills.sandbox.enabled is True
    assert settings.skills.sandbox.require_bubblewrap is False
    assert settings.skills.sandbox.allow_unsafe_local_execution is True
    assert settings.skills.package_directory == BACKEND_ROOT / ".runtime" / "skill-packages"
    assert settings.skills.artifact_directory == BACKEND_ROOT / ".runtime" / "skill-artifacts"
    assert settings.object_storage.bucket == "parrot-test-bucket"
    assert settings.object_storage.download_domain == "https://storage.example.invalid"
    assert settings.memory.vector.enabled is False
    assert settings.memory.vector.uri == "http://vector.example.invalid:19530"
    assert settings.memory.vector.token_ref == "milvus-root-token"
    assert settings.memory.vector.token_ref in settings.memory_credentials.values
    assert settings.memory.embedding.model == "text-embedding-v4"
    assert settings.memory.embedding.credential_ref == "dashscope-api-key"
    assert settings.memory.embedding.extra_body == {"dimensions": 1024, "encoding_format": "float"}
    assert settings.knowledge.embedding.base_url is None
    assert settings.knowledge.embedding.credential_ref is None
    assert settings.knowledge.embedding.allowed_hosts == (
        "127.0.0.1",
        "dashscope.aliyuncs.com",
    )
    assert "dashscope-api-key" not in settings.knowledge_credentials.values
    assert settings.capability_index.enabled is False
    assert settings.capability_index.vector.collection == "parrot_capabilities"
    assert settings.capability_index.vector.metric_type == "COSINE"
    assert settings.capability_index.embedding.credential_ref == "dashscope-api-key"
    assert settings.capability_index.embedding.credential_ref in settings.memory_credentials.values
    assert knowledge_vector_runtime_issue(settings) is None
    assert settings.schedules.default_timezone == "Asia/Shanghai"
    assert isinstance(
        build_runtime(settings, cast(TaskDispatcher, SimpleNamespace())), DurableInProcessRuntime
    )


def test_sit_config_loads_complete_inline_configuration() -> None:
    settings = load_app_config(ROOT / "config" / "sit.toml")

    assert settings.app.environment == "sit"
    assert settings.app.debug is False
    assert settings.database.url.startswith("postgresql+asyncpg://parrot_app:")
    assert settings.object_storage.bucket == "parrot-test-bucket"
    assert settings.memory.vector.token_ref in settings.memory_credentials.values
    assert settings.capability_index.enabled is False
    assert settings.knowledge.embedding.allowed_hosts == (
        "127.0.0.1",
        "dashscope.aliyuncs.com",
    )


def _production_values() -> dict[str, object]:
    content = (ROOT / "config" / "prod.toml").read_text()
    content = content.replace("overridden-by-deployment", secrets.token_urlsafe(32))
    # Build deployment-like values in memory without storing real credentials in fixtures.
    content = re.sub(r"test-only-[a-z-]+", lambda _: secrets.token_urlsafe(36), content)
    return tomllib.loads(content)


def test_prod_config_requires_external_deployment_values() -> None:
    with pytest.raises(RuntimeError, match="Invalid config"):
        load_app_config(ROOT / "config" / "prod.toml")


def test_prod_config_loads_complete_deployment_configuration() -> None:
    settings = AppConfig.model_validate(_production_values())

    assert settings.app.environment == "prod"
    assert settings.app.debug is False
    assert settings.server.reload is False
    assert settings.security.secure_cookies is True
    assert all(origin.startswith("https://") for origin in settings.security.allowed_origins)
    assert (
        len(
            {
                settings.database.url,
                settings.database.platform_url,
                settings.database.migration_url,
            }
        )
        == 3
    )
    assert settings.object_storage.download_domain.startswith("https://")
    assert settings.memory.vector.enabled is False
    assert settings.capability_index.enabled is False


def test_config_rejects_removed_secrets_file_overlay() -> None:
    settings = load_app_config(ROOT / "config" / "dev.toml")
    values = settings.model_dump(mode="python", by_alias=True)
    values["app"]["secrets_file"] = "local.secrets.toml"

    with pytest.raises(ValueError):
        AppConfig.model_validate(values)


def test_capability_relevance_threshold_requires_cosine_metric() -> None:
    settings = load_app_config(ROOT / "config" / "dev.toml")
    values = settings.model_dump(mode="python", by_alias=True)
    values["capability_index"]["enabled"] = True
    values["capability_index"]["vector"]["metric_type"] = "L2"

    with pytest.raises(ValueError, match="capability indexing requires COSINE"):
        AppConfig.model_validate(values)


def test_knowledge_vector_runtime_uses_connection_credentials_not_a_feature_switch() -> None:
    settings = load_app_config(ROOT / "config" / "dev.toml")
    values = settings.model_dump(mode="python", by_alias=True)
    values["knowledge_credentials"] = {"values": {"milvus-root-token": "test-token"}}

    configured = AppConfig.model_validate(values)

    assert knowledge_vector_runtime_issue(configured) is None
    assert configured.knowledge.embedding.base_url is None


def test_missing_config_fails_without_environment_fallback(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="Config file not found"):
        load_app_config(tmp_path / "missing.toml")


def test_prod_rejects_shared_database_roles() -> None:
    settings = AppConfig.model_validate(_production_values())
    values = settings.model_dump(mode="python", by_alias=True)
    shared = "postgresql+asyncpg://same:secret@database/parrot"
    values["database"].update(url=shared, platform_url=shared, migration_url=shared)

    with pytest.raises(ValueError, match="production database roles must use distinct URLs"):
        AppConfig.model_validate(values)


def test_sit_allows_dev_diagnostic_switches() -> None:
    settings = load_app_config(ROOT / "config" / "sit.toml")
    values = settings.model_dump(mode="python", by_alias=True)
    values["ai"].update(debug_log_prompts=True, debug_capture_prompts=True)
    settings = AppConfig.model_validate(values)

    assert settings.ai.debug_log_prompts is True
    assert settings.ai.debug_capture_prompts is True


@pytest.mark.parametrize(
    "section,field",
    [
        ("security", "session_pepper"),
        ("security", "credential_encryption_key"),
        ("object_storage", "access_key"),
        ("object_storage", "secret_key"),
        ("database", "url"),
        ("redis", "url"),
    ],
)
def test_prod_rejects_public_test_secrets(section: str, field: str) -> None:
    values = _production_values()
    # TOML sections are typed at the AppConfig validation boundary.
    section_values = cast(dict[str, object], values[section])
    placeholder = "test-only-never-deploy"
    if field == "url":
        placeholder = "postgresql+asyncpg://test:test-only-password@localhost/parrot"
    if field == "credential_encryption_key":
        placeholder = base64.urlsafe_b64encode(b"test-only-parrot-encryption-key!").decode()
    section_values[field] = placeholder

    with pytest.raises(ValueError, match="not public test placeholders"):
        AppConfig.model_validate(values)


def test_prod_rejects_raw_prompt_terminal_logging() -> None:
    settings = load_app_config(ROOT / "config" / "dev.toml")
    values = settings.model_dump(mode="python", by_alias=True)
    values["app"]["environment"] = "prod"
    values["app"]["debug"] = False
    values["ai"]["debug_log_prompts"] = True

    with pytest.raises(ValueError, match="ai.debug_log_prompts requires app.environment"):
        AppConfig.model_validate(values)


def test_prod_rejects_raw_prompt_capture() -> None:
    settings = load_app_config(ROOT / "config" / "dev.toml")
    values = settings.model_dump(mode="python", by_alias=True)
    values["app"]["environment"] = "prod"
    values["app"]["debug"] = False
    values["ai"]["debug_log_prompts"] = False
    values["ai"]["debug_capture_prompts"] = True

    with pytest.raises(ValueError, match="ai.debug_capture_prompts requires app.environment"):
        AppConfig.model_validate(values)


@pytest.mark.parametrize("environment", ["local", "test", "development", "staging", "production"])
def test_legacy_environment_names_are_rejected(environment: str) -> None:
    settings = load_app_config(ROOT / "config" / "dev.toml")
    values = settings.model_dump(mode="python", by_alias=True)
    values["app"]["environment"] = environment

    with pytest.raises(ValueError):
        AppConfig.model_validate(values)


def test_knowledge_embedded_image_limits_are_format_specific() -> None:
    knowledge = load_app_config(ROOT / "config" / "dev.toml").knowledge
    assert knowledge.max_embedded_images_for(
        "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    ) == min(knowledge.max_pptx_embedded_images, knowledge.max_embedded_images_per_version)
    assert knowledge.max_embedded_images_for(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ) == min(knowledge.max_docx_embedded_images, knowledge.max_embedded_images_per_version)
    assert knowledge.max_embedded_images_for(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    ) == min(knowledge.max_xlsx_embedded_images, knowledge.max_embedded_images_per_version)
    assert (
        knowledge.max_embedded_images_for("text/plain") == knowledge.max_embedded_images_per_version
    )
