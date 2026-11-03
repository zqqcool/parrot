from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import httpx
import pytest
from _agent_runtime_support import credential_cipher
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

import app.modules.embedding_configs.service as embedding_service_module
import app.modules.llm_configs.service as llm_service_module
import app.modules.reranker_configs.service as reranker_service_module
from app.core.agent_runtime import RuntimeLlmProfile
from app.core.config import load_app_config
from app.core.errors import AppError
from app.infrastructure.db.session import DatabaseManager
from app.modules.agent_runtime.contracts import ChatMessage, ModelProviderError
from app.modules.embedding_configs.models import EmbeddingConfig
from app.modules.embedding_configs.schemas import EmbeddingConfigConnectionTestRequest
from app.modules.embedding_configs.service import EmbeddingConfigService
from app.modules.iam.schemas import PrincipalContext
from app.modules.llm_configs.models import LlmConfig
from app.modules.llm_configs.schemas import LlmConfigConnectionTestRequest
from app.modules.llm_configs.service import LlmConfigService
from app.modules.model_configs.connection_test import connection_test_failed
from app.modules.model_providers.embedding import EmbeddingProviderProfile
from app.modules.model_providers.reranker import RerankerProviderProfile
from app.modules.reranker_configs.models import RerankerConfig
from app.modules.reranker_configs.schemas import RerankerConfigConnectionTestRequest
from app.modules.reranker_configs.service import RerankerConfigService

ROOT = Path(__file__).resolve().parents[1]


def _settings():
    return load_app_config(ROOT / "config" / "dev.toml")


def _principal(*permissions: str, tenant_id: str = "tenant_test") -> PrincipalContext:
    return PrincipalContext(
        tenant_id=tenant_id,
        subject_id="user_test",
        username="admin",
        display_name="Admin",
        permissions=permissions,
        tenants=(),
        must_change_password=False,
        request_id="request_test",
    )


def _database() -> DatabaseManager:
    return cast(DatabaseManager, SimpleNamespace(set_tenant=AsyncMock()))


@pytest.mark.asyncio
async def test_llm_connection_uses_the_saved_runtime_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = LlmConfig(
        id="llm_test",
        tenant_id="tenant_test",
        name="Primary",
        provider="openai-compatible",
        model="model-test",
        base_url="https://model.example.test/v1",
        credential_envelope="encrypted-secret",
        temperature=0.4,
        max_tokens=2048,
        thinking_enabled=True,
        status="active",
        is_default=True,
    )
    seen_profiles: list[RuntimeLlmProfile] = []
    seen_messages: list[tuple[ChatMessage, ...]] = []

    class FakeModelClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        async def complete(
            self, profile: RuntimeLlmProfile, messages: tuple[ChatMessage, ...]
        ) -> None:
            seen_profiles.append(profile)
            seen_messages.append(messages)

    monkeypatch.setattr(llm_service_module, "ProviderLlmClient", FakeModelClient)
    session = cast(AsyncSession, SimpleNamespace(scalar=AsyncMock(return_value=model)))
    service = LlmConfigService(session, _database(), credential_cipher(), _settings())

    result = await service.test_connection(
        _principal("llm_configs.manage"), "tenant_test", model.id
    )

    assert result.connected is True
    assert seen_profiles == [
        RuntimeLlmProfile(
            id=model.id,
            provider=model.provider,
            model=model.model,
            base_url=model.base_url,
            credential_envelope=model.credential_envelope,
            temperature=model.temperature,
            max_tokens=model.max_tokens,
            thinking_enabled=model.thinking_enabled,
        )
    ]
    assert seen_messages[0][0].content == "Reply with OK."


@pytest.mark.asyncio
async def test_embedding_connection_uses_saved_model_and_fixed_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = EmbeddingConfig(
        id="embedding_test",
        tenant_id="tenant_test",
        name="Embedding",
        provider="openai_compatible",
        model="text-embedding-v4",
        base_url="https://embedding.example.test/v1",
        credential_envelope="encrypted-secret",
        embedding_dimension=1024,
        configuration_version=1,
        status="active",
    )
    seen_values: list[tuple[str, ...]] = []

    class FakeEmbeddingClient:
        def __init__(
            self,
            _settings: object,
            _cipher: object,
            saved: EmbeddingConfig,
            **_kwargs: object,
        ) -> None:
            assert saved is config

        async def embed(self, values: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
            seen_values.append(values)
            return ((0.1,),)

    monkeypatch.setattr(
        embedding_service_module, "ConfiguredKnowledgeEmbedding", FakeEmbeddingClient
    )
    session = cast(AsyncSession, SimpleNamespace(scalar=AsyncMock(return_value=config)))
    service = EmbeddingConfigService(session, _database(), credential_cipher(), _settings())

    result = await service.test_connection(
        _principal("llm_configs.manage"), "tenant_test", config.id
    )

    assert result.connected is True
    assert seen_values == [("connection test",)]


@pytest.mark.asyncio
async def test_reranker_connection_uses_saved_model_and_fixed_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = RerankerConfig(
        id="reranker_test",
        tenant_id="tenant_test",
        name="Reranker",
        provider="parrot_http",
        model="reranker-model",
        base_url="https://reranker.example.test/v1",
        credential_envelope="encrypted-secret",
        status="active",
    )
    seen_calls: list[tuple[str, tuple[str, ...], int]] = []

    class FakeRerankerClient:
        def __init__(
            self,
            _settings: object,
            _cipher: object,
            saved: RerankerConfig,
            **_kwargs: object,
        ) -> None:
            assert saved is config

        async def rerank(
            self, query: str, documents: tuple[str, ...], top_n: int
        ) -> tuple[object, ...]:
            seen_calls.append((query, documents, top_n))
            return ()

    monkeypatch.setattr(reranker_service_module, "ConfiguredReranker", FakeRerankerClient)
    session = cast(AsyncSession, SimpleNamespace(scalar=AsyncMock(return_value=config)))
    service = RerankerConfigService(session, _database(), credential_cipher(), _settings())

    result = await service.test_connection(
        _principal("llm_configs.manage"), "tenant_test", config.id
    )

    assert result.connected is True
    assert seen_calls == [("connection test", ("connection test",), 1)]


@pytest.mark.asyncio
async def test_reranker_draft_cannot_reuse_credentials_from_another_provider() -> None:
    saved = RerankerConfig(
        id="reranker_test",
        tenant_id="tenant_test",
        name="Legacy reranker",
        provider="parrot_http",
        model="legacy-model",
        base_url="https://reranker.example.test/v1",
        credential_envelope="encrypted-secret",
        status="active",
    )
    service = RerankerConfigService(
        cast(AsyncSession, SimpleNamespace(scalar=AsyncMock(return_value=saved))),
        _database(),
        credential_cipher(),
        _settings(),
    )

    with pytest.raises(AppError) as error:
        await service.test_draft_connection(
            _principal("llm_configs.manage"),
            "tenant_test",
            RerankerConfigConnectionTestRequest(
                config_id=saved.id,
                provider="aliyun_bailian",
                model="qwen3-rerank",
                base_url=("https://workspace-test.cn-beijing.maas.aliyuncs.com/compatible-api/v1"),
            ),
        )

    assert error.value.code == "MODEL_PROVIDER_CREDENTIAL_INVALID"
    assert error.value.details == [
        {"field": "api_key", "reason": "Required by the selected provider"}
    ]


@pytest.mark.asyncio
async def test_connection_failure_is_safe_and_permission_is_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = LlmConfig(
        id="llm_test",
        tenant_id="tenant_test",
        name="Primary",
        provider="openai-compatible",
        model="model-test",
        base_url="https://model.example.test/v1",
        credential_envelope="encrypted-secret",
        temperature=0.2,
        max_tokens=4096,
        thinking_enabled=False,
        prompt_cache_enabled=False,
        status="active",
        is_default=True,
    )

    class FailingModelClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        async def complete(self, *_args: object) -> None:
            raise ModelProviderError("private provider failure")

    monkeypatch.setattr(llm_service_module, "ProviderLlmClient", FailingModelClient)
    session = cast(AsyncSession, SimpleNamespace(scalar=AsyncMock(return_value=model)))
    service = LlmConfigService(session, _database(), credential_cipher(), _settings())

    with pytest.raises(AppError) as forbidden:
        await service.test_connection(_principal("llm_configs.read"), "tenant_test", model.id)
    with pytest.raises(AppError) as failed:
        await service.test_connection(_principal("llm_configs.manage"), "tenant_test", model.id)

    assert forbidden.value.code == "FORBIDDEN"
    assert failed.value.code == "MODEL_CONFIG_CONNECTION_FAILED"
    assert failed.value.status_code == 502
    assert "private provider failure" not in failed.value.message


def test_connection_failure_exposes_only_structured_redacted_provider_details() -> None:
    request = httpx.Request("POST", "https://provider.example.test/v1/embeddings")
    response = httpx.Response(
        401,
        request=request,
        json={
            "error": {
                "code": "Unauthorized",
                "type": "authentication_error",
                "message": "Invalid API key ark-secret-value-12345678",
                "request_id": "provider_req_123",
            }
        },
    )
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as upstream:
        provider_error = ModelProviderError("Model provider request failed")
        provider_error.__cause__ = upstream
    else:  # pragma: no cover - defensive assertion for the test fixture
        raise AssertionError("Expected provider response to fail")

    failed = connection_test_failed(provider_error)

    assert failed.details == [
        {"field": "upstream_http_status", "reason": "401 Unauthorized"},
        {"field": "upstream_error_code", "reason": "Unauthorized"},
        {"field": "upstream_error_type", "reason": "authentication_error"},
        {"field": "upstream_message", "reason": "Invalid API key [REDACTED]"},
        {"field": "upstream_request_id", "reason": "provider_req_123"},
    ]
    assert "ark-secret-value" not in repr(failed.details)


@pytest.mark.asyncio
async def test_llm_draft_connection_uses_typed_unsaved_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_profiles: list[RuntimeLlmProfile] = []

    class FakeModelClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        async def complete(
            self, profile: RuntimeLlmProfile, _messages: tuple[ChatMessage, ...]
        ) -> None:
            seen_profiles.append(profile)

    monkeypatch.setattr(llm_service_module, "ProviderLlmClient", FakeModelClient)
    session = cast(AsyncSession, SimpleNamespace())
    service = LlmConfigService(session, _database(), credential_cipher(), _settings())

    result = await service.test_draft_connection(
        _principal("llm_configs.manage"),
        "tenant_test",
        LlmConfigConnectionTestRequest(
            provider="volcengine_ark",
            model="doubao-seed-2-0-mini-260215",
            base_url="https://ark.cn-beijing.volces.com/api/v3",
            api_key=SecretStr("draft-secret"),
        ),
    )

    assert result.connected is True
    assert seen_profiles[0].provider == "volcengine_ark"
    assert seen_profiles[0].credential_envelope != "draft-secret"


@pytest.mark.asyncio
async def test_embedding_draft_connection_uses_native_provider_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_profiles: list[EmbeddingProviderProfile] = []

    class FakeEmbeddingClient:
        def __init__(self, profile: EmbeddingProviderProfile, **_kwargs: object) -> None:
            seen_profiles.append(profile)

        async def embed(self, _values: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
            return ((0.1,),)

    monkeypatch.setattr(embedding_service_module, "ProviderEmbeddingClient", FakeEmbeddingClient)
    session = cast(AsyncSession, SimpleNamespace())
    service = EmbeddingConfigService(session, _database(), credential_cipher(), _settings())

    result = await service.test_draft_connection(
        _principal("llm_configs.manage"),
        "tenant_test",
        EmbeddingConfigConnectionTestRequest(
            provider="volcengine_ark",
            model="doubao-embedding-vision-251215",
            base_url="https://ark.cn-beijing.volces.com/api/v3",
            api_key=SecretStr("draft-secret"),
            embedding_dimension=2048,
        ),
    )

    assert result.connected is True
    profile = seen_profiles[0]
    assert profile.provider == "volcengine_ark"
    assert profile.api_key == "draft-secret"
    assert profile.embedding_dimension == 2048


@pytest.mark.asyncio
async def test_reranker_draft_connection_uses_bailian_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_profiles: list[RerankerProviderProfile] = []

    class FakeRerankerClient:
        def __init__(self, profile: RerankerProviderProfile, **_kwargs: object) -> None:
            seen_profiles.append(profile)

        async def rerank(self, *_args: object) -> tuple[object, ...]:
            return ()

    monkeypatch.setattr(reranker_service_module, "ProviderRerankerClient", FakeRerankerClient)
    service = RerankerConfigService(
        cast(AsyncSession, SimpleNamespace()),
        _database(),
        credential_cipher(),
        _settings(),
    )

    result = await service.test_draft_connection(
        _principal("llm_configs.manage"),
        "tenant_test",
        RerankerConfigConnectionTestRequest(
            provider="aliyun_bailian",
            model="qwen3-rerank",
            base_url=("https://workspace-test.cn-beijing.maas.aliyuncs.com/compatible-api/v1"),
            api_key=SecretStr("draft-api-key"),
        ),
    )

    assert result.connected is True
    profile = seen_profiles[0]
    assert profile.provider == "aliyun_bailian"
    assert profile.credential.api_key == "draft-api-key"
