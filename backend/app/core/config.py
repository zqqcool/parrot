from __future__ import annotations

import base64
import binascii
import tomllib
from pathlib import Path
from typing import Any, Literal, cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

from app.core.config_secrets import validate_production_secrets

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = BACKEND_ROOT / "config" / "dev.toml"


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class AppSection(FrozenModel):
    name: str
    environment: Literal["dev", "sit", "prod"]
    debug: bool = False


class ServerSection(FrozenModel):
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    reload: bool = False


class ApiSection(FrozenModel):
    prefix: str = "/api/v1"


class LoggingSection(FrozenModel):
    level: str = "INFO"
    json_output: bool = Field(default=False, alias="json")

    @model_validator(mode="after")
    def validate_level(self) -> LoggingSection:
        supported = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if self.level.upper() not in supported:
            raise ValueError("logging.level must be a standard Python logging level")
        return self


class DatabaseSection(FrozenModel):
    enabled: bool = True
    url: str
    platform_url: str
    migration_url: str
    pool_size: int = Field(default=5, ge=1, le=50)
    max_overflow: int = Field(default=10, ge=0, le=100)


class RedisSection(FrozenModel):
    enabled: bool = True
    url: str
    key_prefix: str = "parrot"


class TaskiqSection(FrozenModel):
    """Redis Stream delivery and TaskIQ scheduler settings.

    PostgreSQL remains the source of truth for business state.  This section only
    controls TaskIQ delivery, acknowledgement recovery, and durable schedules.
    """

    queue_name: str = Field(default="parrot:tasks", min_length=1, max_length=191)
    consumer_group: str = Field(default="parrot", min_length=1, max_length=191)
    schedule_prefix: str = Field(default="parrot:schedules", min_length=1, max_length=191)
    dispatch_delay_seconds: int = Field(default=3, ge=1, le=60)
    stream_maxlen: int = Field(default=100_000, ge=1_000, le=10_000_000)
    unacknowledged_idle_seconds: int = Field(default=600, ge=30, le=86_400)


class SecuritySection(FrozenModel):
    session_cookie_name: str = "parrot_session"
    visitor_cookie_name: str = "parrot_visitor"
    session_pepper: str
    credential_encryption_key: SecretStr
    secure_cookies: bool = True
    session_absolute_seconds: int = Field(default=28800, ge=300)
    session_idle_seconds: int = Field(default=1800, ge=60)
    password_min_length: int = Field(default=12, ge=10, le=128)
    allowed_origins: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_credential_encryption_key(self) -> SecuritySection:
        encoded = self.credential_encryption_key.get_secret_value()
        if encoded.startswith("overridden-by-"):
            return self
        try:
            padded = encoded + "=" * (-len(encoded) % 4)
            decoded = base64.b64decode(padded, altchars=b"-_", validate=True)
        except (ValueError, binascii.Error) as error:
            raise ValueError(
                "security.credential_encryption_key must use URL-safe base64"
            ) from error
        if len(decoded) != 32:
            raise ValueError("security.credential_encryption_key must decode to exactly 32 bytes")
        return self


class AnonymousSection(FrozenModel):
    session_ttl_seconds: int = Field(default=2592000, ge=300)
    rate_limit_requests: int = Field(default=30, ge=1)
    rate_limit_window_seconds: int = Field(default=60, ge=1)


class LimitsSection(FrozenModel):
    max_text_chars: int = Field(default=12000, ge=1)
    max_audio_ref_chars: int = Field(default=512, ge=1)


class AiSection(FrozenModel):
    allowed_model_hosts: tuple[str, ...] = ()
    debug_log_prompts: bool = False
    debug_capture_prompts: bool = False
    agent_max_tool_rounds: int = Field(default=6, ge=1, le=16)
    agent_max_tool_calls: int = Field(default=12, ge=1, le=64)
    agent_max_consecutive_tool_errors: int = Field(default=3, ge=1, le=16)
    agent_max_output_tokens: int = Field(default=4_096, ge=128, le=32_768)
    agent_model_retry_attempts: int = Field(default=2, ge=0, le=5)
    agent_max_control_plane_replans: int = Field(default=2, ge=0, le=3)
    agent_max_finalization_replans: int = Field(default=1, ge=0, le=3)
    agent_direct_rendering_enabled: bool = True
    # Deprecated input compatibility only; the unified knowledge Loop ignores this key.
    knowledge_parallel_evidence_enabled: bool = True
    agent_loop_subagents_enabled: bool = True
    agent_max_subagent_tasks: int = Field(default=5, ge=1, le=5)
    agent_max_parallel_subagents: int = Field(default=3, ge=1, le=5)
    agent_max_supporting_skills: int = Field(default=3, ge=0, le=8)
    max_parallel_tool_calls: int = Field(default=3, ge=1, le=8)
    capability_exact_repeat_limit: int = Field(default=1, ge=1, le=5)
    capability_similar_repeat_limit: int = Field(default=2, ge=1, le=5)
    capability_similarity_threshold: float = Field(default=0.6, ge=0.1, le=1.0)


class MemoryCredentialsSection(FrozenModel):
    values: dict[str, str] = Field(default_factory=dict)


class McpRuntimeSection(FrozenModel):
    allowed_hosts: tuple[str, ...] = ()
    connect_timeout_seconds: int = Field(default=15, ge=1, le=120)
    tool_timeout_seconds: int = Field(default=90, ge=1, le=900)
    max_discovered_tools_per_server: int = Field(default=100, ge=1, le=500)
    max_tool_result_bytes: int = Field(default=262_144, ge=1_024, le=1_048_576)
    allow_stdio: bool = False


class MemoryEmbeddingSection(FrozenModel):
    base_url: str | None = None
    model: str = "bge-m3"
    credential_ref: str | None = None
    allowed_hosts: tuple[str, ...] = ()
    extra_body: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: int = Field(default=30, ge=1, le=120)


class MemoryVectorSection(FrozenModel):
    enabled: bool = False
    uri: str | None = None
    database: str = "default"
    collection: str = "parrot_memory"
    token_ref: str | None = None
    embedding_dimension: int = Field(default=1024, ge=8, le=16_384)
    metric_type: Literal["COSINE", "IP", "L2"] = "COSINE"


class MemoryRuntimeSection(FrozenModel):
    context_limit: int = Field(default=12, ge=1, le=50)
    context_max_tokens: int = Field(default=1_800, ge=128, le=8_000)
    search_limit: int = Field(default=20, ge=1, le=50)
    max_content_chars: int = Field(default=8_000, ge=128, le=32_000)
    embedding: MemoryEmbeddingSection = MemoryEmbeddingSection()
    vector: MemoryVectorSection = MemoryVectorSection()


class ConversationMessagesSection(FrozenModel):
    """Retention policy for unrefined, channel-originated transcript rows."""

    retention_days: int = Field(default=30, ge=1, le=3650)


class ScriptRuntimeSection(FrozenModel):
    enabled: bool = False
    default_timeout_seconds: int = Field(default=30, ge=1, le=300)
    max_timeout_seconds: int = Field(default=120, ge=1, le=900)


class RuntimeSection(FrozenModel):
    request_timeout_seconds: int = Field(default=360, ge=5, le=1800)
    poll_interval_seconds: float = Field(default=0.5, ge=0.1, le=10)
    lease_heartbeat_seconds: float = Field(default=15, ge=1, le=300)
    history_turns: int = Field(default=16, ge=1, le=100)
    history_max_tokens: int = Field(default=1_800, ge=128, le=8_000)
    default_timezone: str = Field(default="UTC", min_length=1, max_length=64)
    script: ScriptRuntimeSection = ScriptRuntimeSection()


class SchedulesSection(FrozenModel):
    default_timezone: str = Field(default="UTC", min_length=1, max_length=64)


class MediaSection(FrozenModel):
    max_agent_avatar_bytes: int = Field(default=2 * 1024 * 1024, ge=1, le=10 * 1024 * 1024)
    max_user_avatar_bytes: int = Field(default=2 * 1024 * 1024, ge=1, le=10 * 1024 * 1024)


class KnowledgeEmbeddingSection(FrozenModel):
    base_url: str | None = None
    model: str = "bge-m3"
    credential_ref: str | None = None
    allowed_hosts: tuple[str, ...] = ()
    timeout_seconds: int = Field(default=30, ge=1, le=120)


class KnowledgeRerankerSection(FrozenModel):
    allowed_hosts: tuple[str, ...] = ()
    timeout_seconds: int = Field(default=30, ge=1, le=120)


class KnowledgeVectorSection(FrozenModel):
    uri: str | None = None
    database: str = "default"
    collection: str = "parrot_knowledge"
    token_ref: str | None = None
    embedding_dimension: int = Field(default=1024, ge=8, le=16_384)
    metric_type: Literal["COSINE", "IP", "L2"] = "COSINE"
    candidate_multiplier: int = Field(default=4, ge=2, le=20)
    reciprocal_rank_constant: int = Field(default=60, ge=1, le=1_000)


class KnowledgeSection(FrozenModel):
    max_upload_bytes: int = Field(default=50 * 1024 * 1024, ge=1_024, le=100 * 1024 * 1024)
    staging_retention_hours: int = Field(default=24, ge=1, le=168)
    max_extracted_chars: int = Field(default=2_000_000, ge=10_000, le=10_000_000)
    max_pdf_pages: int = Field(default=1_000, ge=1, le=10_000)
    max_pptx_slides: int = Field(default=200, ge=1, le=2_000)
    max_pptx_embedded_images: int = Field(default=500, ge=0, le=5_000)
    max_docx_embedded_images: int = Field(default=200, ge=0, le=2_000)
    max_xlsx_sheets: int = Field(default=50, ge=1, le=500)
    max_xlsx_rows_per_region: int = Field(default=2_000, ge=10, le=50_000)
    max_xlsx_embedded_images: int = Field(default=200, ge=0, le=2_000)
    max_embedded_images_per_version: int = Field(default=500, ge=0, le=5_000)
    slide_render_enabled: bool = True
    evidence_max_groups: int = Field(default=6, ge=1, le=50)
    evidence_max_units: int = Field(default=8, ge=1, le=50)
    evidence_max_media: int = Field(default=8, ge=1, le=50)
    evidence_adjacent_window: int = Field(default=1, ge=0, le=10)
    embedding: KnowledgeEmbeddingSection = KnowledgeEmbeddingSection()
    reranker: KnowledgeRerankerSection = KnowledgeRerankerSection()
    vector: KnowledgeVectorSection = KnowledgeVectorSection()

    def max_embedded_images_for(self, content_type: str) -> int:
        """Per-format embed budgets, always capped by the version-wide ceiling."""
        per_version = self.max_embedded_images_per_version
        normalized = content_type.lower().split(";", 1)[0].strip()
        if normalized.endswith("presentationml.presentation") or normalized.endswith(
            "presentationml.slideshow"
        ):
            return min(self.max_pptx_embedded_images, per_version)
        if normalized.endswith("wordprocessingml.document"):
            return min(self.max_docx_embedded_images, per_version)
        if normalized.endswith("spreadsheetml.sheet"):
            return min(self.max_xlsx_embedded_images, per_version)
        return per_version


class CapabilityIndexSection(FrozenModel):
    """Deployment-owned capability retrieval; never editable by a tenant."""

    enabled: bool = False
    embedding: KnowledgeEmbeddingSection = KnowledgeEmbeddingSection()
    vector: KnowledgeVectorSection = KnowledgeVectorSection(collection="parrot_capabilities")


class ObjectStorageSection(FrozenModel):
    provider: Literal["qiniu"] = "qiniu"
    bucket: str = Field(min_length=3, max_length=255)
    key_prefix: str = Field(default="parrot", pattern="^[a-zA-Z0-9][a-zA-Z0-9._/-]*$")
    download_domain: str = Field(min_length=1)
    upload_token_seconds: int = Field(default=900, ge=300, le=3600)
    access_key: str = Field(min_length=1)
    secret_key: str = Field(min_length=1)


class SkillsSection(FrozenModel):
    package_directory: Path
    artifact_directory: Path
    max_package_bytes: int = Field(default=50 * 1024 * 1024, ge=1, le=50 * 1024 * 1024)
    max_artifact_bytes: int = Field(default=200 * 1024 * 1024, ge=1, le=500 * 1024 * 1024)
    sandbox: SkillSandboxSection
    build: SkillBuildSection


class SkillSandboxSection(FrozenModel):
    enabled: bool = False
    session_directory: Path
    python_executable: str = "python3"
    node_executable: str = "node"
    npm_executable: str = "npm"
    shell_executable: str = "/bin/sh"
    bwrap_path: str = "bwrap"
    require_bubblewrap: bool = True
    allow_unsafe_local_execution: bool = False
    default_timeout_seconds: int = Field(default=60, ge=1, le=300)
    max_timeout_seconds: int = Field(default=300, ge=1, le=900)
    max_output_bytes: int = Field(default=262_144, ge=1_024, le=1_048_576)


class SkillBuildSection(FrozenModel):
    session_directory: Path
    timeout_seconds: int = Field(default=300, ge=1, le=900)
    pip_index_url: str | None = None
    npm_registry: str | None = None


class AppConfig(FrozenModel):
    app: AppSection
    server: ServerSection
    api: ApiSection
    logging: LoggingSection
    database: DatabaseSection
    redis: RedisSection
    taskiq: TaskiqSection = TaskiqSection()
    security: SecuritySection
    anonymous: AnonymousSection
    limits: LimitsSection
    ai: AiSection
    memory_credentials: MemoryCredentialsSection = MemoryCredentialsSection()
    knowledge_credentials: MemoryCredentialsSection = MemoryCredentialsSection()
    mcp: McpRuntimeSection = McpRuntimeSection()
    memory: MemoryRuntimeSection = MemoryRuntimeSection()
    conversation_messages: ConversationMessagesSection = ConversationMessagesSection()
    media: MediaSection
    knowledge: KnowledgeSection = KnowledgeSection()
    capability_index: CapabilityIndexSection = CapabilityIndexSection()
    object_storage: ObjectStorageSection
    skills: SkillsSection
    runtime: RuntimeSection = RuntimeSection()
    schedules: SchedulesSection = SchedulesSection()

    @model_validator(mode="after")
    def validate_environment(self) -> AppConfig:
        if not self.api.prefix.startswith("/") or self.api.prefix.endswith("/"):
            raise ValueError("api.prefix must start with / and must not end with /")
        if self.ai.debug_log_prompts and self.app.environment == "prod":
            raise ValueError("ai.debug_log_prompts requires app.environment = dev or sit")
        if self.ai.debug_capture_prompts and self.app.environment == "prod":
            raise ValueError("ai.debug_capture_prompts requires app.environment = dev or sit")
        if self.app.environment == "prod":
            self._validate_production()
        _validate_runtime(self)
        _validate_memory_vector(self)
        _validate_knowledge_vector(self)
        _validate_capability_index(self)
        return self

    def _validate_production(self) -> None:
        validate_production_secrets(self)
        if self.app.debug or self.server.reload:
            raise ValueError("production cannot enable debug or reload")
        if not self.security.secure_cookies:
            raise ValueError("production requires secure cookies")
        if len(self.security.session_pepper) < 32:
            raise ValueError("production session pepper must contain at least 32 characters")
        credential_key = self.security.credential_encryption_key.get_secret_value()
        if credential_key.startswith("overridden-by-"):
            raise ValueError("production requires an external credential encryption key")
        if not self.security.allowed_origins or any(
            not origin.startswith("https://") for origin in self.security.allowed_origins
        ):
            raise ValueError("production requires explicit HTTPS origins")
        database_urls = {
            self.database.url,
            self.database.platform_url,
            self.database.migration_url,
        }
        if len(database_urls) != 3:
            raise ValueError("production database roles must use distinct URLs")
        self._validate_production_skill_storage()
        self._validate_production_skill_sandbox()
        self._validate_production_memory()
        self._validate_production_knowledge()
        self._validate_production_object_storage()

    def _validate_production_skill_sandbox(self) -> None:
        if self.skills.sandbox.session_directory.is_relative_to(BACKEND_ROOT.parent):
            raise ValueError("production skill sandbox sessions must be outside the repository")
        if self.skills.build.session_directory.is_relative_to(BACKEND_ROOT.parent):
            raise ValueError("production Skill build sessions must be outside the repository")
        if self.skills.sandbox.enabled and not self.skills.sandbox.require_bubblewrap:
            raise ValueError("production Skill execution requires bubblewrap isolation")
        if self.skills.sandbox.allow_unsafe_local_execution:
            raise ValueError("production cannot allow unsafe local Skill execution")

    def _validate_production_skill_storage(self) -> None:
        if self.skills.package_directory.is_relative_to(BACKEND_ROOT.parent):
            raise ValueError("production skill storage must be outside the repository")
        if self.skills.artifact_directory.is_relative_to(BACKEND_ROOT.parent):
            raise ValueError("production Skill artifacts must be outside the repository")
        if self.skills.artifact_directory == self.skills.package_directory:
            raise ValueError(
                "production Skill source packages and artifacts must use separate directories"
            )

    def _validate_production_object_storage(self) -> None:
        if not self.object_storage.download_domain.startswith("https://"):
            raise ValueError("production object storage download domain must use HTTPS")
        if any(
            value.startswith("overridden-by-")
            for value in (
                self.object_storage.access_key,
                self.object_storage.secret_key,
            )
        ):
            raise ValueError("production requires external Qiniu credentials")

    def _validate_production_memory(self) -> None:
        vector = self.memory.vector
        embedding = self.memory.embedding
        if not vector.enabled:
            return
        if not vector.uri or not vector.uri.startswith("https://"):
            raise ValueError("production memory vector service requires an HTTPS URI")
        if not vector.token_ref or vector.token_ref not in self.memory_credentials.values:
            raise ValueError(
                "production memory vector service requires a configured token reference"
            )
        if not embedding.base_url or not embedding.base_url.startswith("https://"):
            raise ValueError("production memory embedding service requires an HTTPS URL")
        if not embedding.credential_ref or (
            embedding.credential_ref not in self.memory_credentials.values
        ):
            raise ValueError(
                "production memory embedding requires a configured credential reference"
            )

    def _validate_production_knowledge(self) -> None:
        vector = self.knowledge.vector
        if vector.uri is None and vector.token_ref is None:
            return
        if not vector.uri or not vector.uri.startswith("https://"):
            raise ValueError("production knowledge vector service requires an HTTPS URI")
        if not vector.token_ref or vector.token_ref not in self.knowledge_credentials.values:
            raise ValueError(
                "production knowledge vector service requires a configured token reference"
            )


def _validate_runtime(config: AppConfig) -> None:
    try:
        ZoneInfo(config.runtime.default_timezone)
    except ZoneInfoNotFoundError as error:
        raise ValueError("runtime.default_timezone must be an IANA timezone") from error
    try:
        ZoneInfo(config.schedules.default_timezone)
    except ZoneInfoNotFoundError as error:
        raise ValueError("schedules.default_timezone must be an IANA timezone") from error
    if config.runtime.script.default_timeout_seconds > config.runtime.script.max_timeout_seconds:
        raise ValueError("runtime.script.default_timeout_seconds cannot exceed max_timeout_seconds")
    if config.runtime.script.enabled and not config.skills.sandbox.enabled:
        raise ValueError("runtime.script.enabled requires skills.sandbox.enabled")
    if config.app.environment == "prod" and not config.ai.allowed_model_hosts:
        raise ValueError("production runtime requires allowed_model_hosts")


def _validate_memory_vector(config: AppConfig) -> None:
    vector = config.memory.vector
    embedding = config.memory.embedding
    if not vector.enabled:
        return
    if not vector.uri or not vector.token_ref:
        raise ValueError("enabled memory vector indexing requires URI and token reference")
    if vector.token_ref not in config.memory_credentials.values:
        raise ValueError("memory vector token reference is unavailable")
    if not embedding.base_url or not embedding.credential_ref:
        raise ValueError("enabled memory vector indexing requires an embedding endpoint")
    if embedding.credential_ref not in config.memory_credentials.values:
        raise ValueError("memory embedding credential reference is unavailable")


def _validate_knowledge_vector(config: AppConfig) -> None:
    # Knowledge spaces opt into vectors through their embedding configuration.
    # A deployment may intentionally serve only lexical spaces, so connection
    # availability is validated at the point a vector space is configured.
    del config


def _validate_capability_index(config: AppConfig) -> None:
    section = config.capability_index
    if not section.enabled:
        return
    vector = section.vector
    embedding = section.embedding
    if not vector.uri or not vector.token_ref:
        raise ValueError("enabled capability indexing requires a vector URI and token reference")
    if vector.metric_type != "COSINE":
        raise ValueError("capability indexing requires COSINE metric for relevance thresholds")
    if vector.token_ref not in config.memory_credentials.values:
        raise ValueError("capability vector token reference is unavailable")
    if not embedding.base_url or not embedding.credential_ref:
        raise ValueError("enabled capability indexing requires an embedding endpoint")
    if embedding.credential_ref not in config.memory_credentials.values:
        raise ValueError("capability embedding credential reference is unavailable")


def knowledge_vector_runtime_issue(config: AppConfig) -> str | None:
    """Return a safe operator-facing reason when vector retrieval cannot start."""
    vector = config.knowledge.vector
    if not vector.uri:
        return "knowledge vector URI is not configured"
    if not vector.token_ref:
        return "knowledge vector credential reference is not configured"
    if not config.knowledge_credentials.values.get(vector.token_ref):
        return "knowledge vector credential reference is unavailable"
    return None


def load_app_config(path: Path | str = DEFAULT_CONFIG_PATH) -> AppConfig:
    config_path = Path(path).expanduser().resolve()
    raw = _load_toml(config_path)
    app_values = raw.get("app")
    if not isinstance(app_values, dict):
        raise RuntimeError("Missing config section: app")
    _resolve_storage_paths(raw, config_path)

    try:
        return AppConfig.model_validate(raw)
    except ValueError:
        # Pydantic validation errors can include raw credentials from the input mapping.
        raise RuntimeError(f"Invalid config: {config_path}") from None


def _load_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise RuntimeError(f"Config file not found: {path}")
    with path.open("rb") as source:
        return tomllib.load(source)


def _resolve_storage_paths(raw: dict[str, Any], config_path: Path) -> None:
    _resolve_configured_path(raw, "skills", "package_directory", config_path)
    _resolve_configured_path(raw, "skills", "artifact_directory", config_path)
    skills = raw.get("skills")
    if isinstance(skills, dict):
        typed_skills = cast(dict[str, Any], skills)
        sandbox = typed_skills.get("sandbox")
        if isinstance(sandbox, dict):
            _resolve_configured_path(
                cast(dict[str, Any], sandbox), "", "session_directory", config_path
            )
        build = typed_skills.get("build")
        if isinstance(build, dict):
            _resolve_configured_path(
                cast(dict[str, Any], build), "", "session_directory", config_path
            )


def _resolve_configured_path(
    raw: dict[str, Any], section: str, field: str, config_path: Path
) -> None:
    values = raw if not section else raw.get(section)
    if not isinstance(values, dict):
        return
    typed_values = cast(dict[str, Any], values)
    configured_value = typed_values.get(field)
    if not configured_value:
        return
    path = Path(str(configured_value)).expanduser()
    if not path.is_absolute():
        path = config_path.parent / path
    typed_values[field] = str(path.resolve())
