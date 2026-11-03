import base64
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import SecretStr, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import load_app_config
from app.core.errors import AppError
from app.infrastructure.credential_cipher import (
    CredentialCipher,
    CredentialCipherError,
    embedding_credential_context,
    reranker_credential_context,
)
from app.infrastructure.db.session import DatabaseManager
from app.modules.embedding_configs.models import EmbeddingConfig
from app.modules.embedding_configs.schemas import (
    EmbeddingConfigCreateRequest,
    EmbeddingConfigUpdateRequest,
)
from app.modules.embedding_configs.service import EmbeddingConfigService
from app.modules.iam.schemas import PrincipalContext
from app.modules.knowledge.schemas import (
    KnowledgeSpaceCreateRequest,
    KnowledgeSpaceRetrievalUpdateRequest,
)
from app.modules.model_configs.endpoint_policy import validate_model_endpoint
from app.modules.model_providers.reranker_credentials import decode_reranker_credential
from app.modules.reranker_configs.models import RerankerConfig
from app.modules.reranker_configs.schemas import (
    RerankerConfigCreateRequest,
    RerankerConfigUpdateRequest,
)
from app.modules.reranker_configs.service import RerankerConfigService

ROOT = Path(__file__).resolve().parents[1]


def _key(value: bytes = b"0" * 32) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


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


def _settings():
    return load_app_config(ROOT / "config" / "dev.toml")


def test_retrieval_credentials_use_independent_authenticated_contexts() -> None:
    cipher = CredentialCipher(_key())
    embedding = cipher.encrypt("embedding-secret", context=embedding_credential_context("embed_1"))
    reranker = cipher.encrypt("reranker-secret", context=reranker_credential_context("rerank_1"))

    assert (
        cipher.decrypt(embedding, context=embedding_credential_context("embed_1"))
        == "embedding-secret"
    )
    assert (
        cipher.decrypt(reranker, context=reranker_credential_context("rerank_1"))
        == "reranker-secret"
    )
    with pytest.raises(CredentialCipherError):
        cipher.decrypt(embedding, context=reranker_credential_context("embed_1"))


@pytest.mark.asyncio
async def test_embedding_config_encrypts_credentials_and_uses_its_own_table_model() -> None:
    cipher = CredentialCipher(_key())
    add = Mock()

    async def flush() -> None:
        cast(EmbeddingConfig, add.call_args.args[0]).status = "active"

    session = cast(AsyncSession, SimpleNamespace(add=add, flush=AsyncMock(side_effect=flush)))
    service = EmbeddingConfigService(
        session,
        cast(DatabaseManager, SimpleNamespace(set_tenant=AsyncMock())),
        cipher,
        _settings(),
    )

    view = await service.create(
        _principal("llm_configs.manage"),
        "tenant_test",
        EmbeddingConfigCreateRequest.model_validate(
            {
                "name": "Knowledge embedding",
                "model": "text-embedding-3-large",
                "base_url": "http://127.0.0.1:11434/v1",
                "api_key": "embedding-secret",
                "embedding_dimension": 1024,
            }
        ),
    )

    stored = cast(EmbeddingConfig, add.call_args_list[0].args[0])
    assert stored.credential_envelope != "embedding-secret"
    assert (
        cipher.decrypt(
            cast(str, stored.credential_envelope), context=embedding_credential_context(stored.id)
        )
        == "embedding-secret"
    )
    assert view.credential_configured is True
    assert "credential_envelope" not in view.model_dump()


@pytest.mark.asyncio
async def test_bailian_reranker_config_encrypts_api_key() -> None:
    cipher = CredentialCipher(_key())
    add = Mock()

    async def flush() -> None:
        cast(RerankerConfig, add.call_args.args[0]).status = "active"

    service = RerankerConfigService(
        cast(AsyncSession, SimpleNamespace(add=add, flush=AsyncMock(side_effect=flush))),
        cast(DatabaseManager, SimpleNamespace(set_tenant=AsyncMock())),
        cipher,
        _settings(),
    )

    view = await service.create(
        _principal("llm_configs.manage"),
        "tenant_test",
        RerankerConfigCreateRequest.model_validate(
            {
                "name": "Bailian reranker",
                "provider": "aliyun_bailian",
                "model": "qwen3-rerank",
                "base_url": (
                    "https://workspace-test.cn-beijing.maas.aliyuncs.com/compatible-api/v1"
                ),
                "api_key": "test-api-key",
            }
        ),
    )

    stored = cast(RerankerConfig, add.call_args_list[0].args[0])
    decrypted = cipher.decrypt(
        cast(str, stored.credential_envelope),
        context=reranker_credential_context(stored.id),
    )
    credential = decode_reranker_credential(decrypted, "api_key")
    assert credential.api_key == "test-api-key"
    assert "test-api-key" not in cast(str, stored.credential_envelope)
    assert view.credential_configured is True


@pytest.mark.asyncio
async def test_reranker_provider_switch_requires_new_endpoint_and_uses_model_default() -> None:
    reranker = RerankerConfig(
        id="reranker_test",
        tenant_id="tenant_test",
        name="Legacy reranker",
        provider="parrot_http",
        model="legacy-model",
        base_url="https://reranker.example.test/v1",
        credential_envelope="v1.encrypted",
        status="active",
    )
    session = cast(
        AsyncSession,
        SimpleNamespace(add=Mock(), scalar=AsyncMock(return_value=reranker), flush=AsyncMock()),
    )
    service = RerankerConfigService(
        session,
        cast(DatabaseManager, SimpleNamespace(set_tenant=AsyncMock())),
        CredentialCipher(_key()),
        _settings(),
    )

    with pytest.raises(AppError) as missing_endpoint:
        await service.update(
            _principal("llm_configs.manage"),
            "tenant_test",
            reranker.id,
            RerankerConfigUpdateRequest(
                provider="aliyun_bailian",
                api_key=SecretStr("new-api-key"),
            ),
        )

    assert missing_endpoint.value.code == "MODEL_CONFIG_ENDPOINT_INVALID"

    with pytest.raises(AppError) as missing_credential:
        await service.update(
            _principal("llm_configs.manage"),
            "tenant_test",
            reranker.id,
            RerankerConfigUpdateRequest(
                provider="aliyun_bailian",
                base_url=("https://workspace-test.cn-beijing.maas.aliyuncs.com/compatible-api/v1"),
            ),
        )

    assert missing_credential.value.code == "MODEL_PROVIDER_CREDENTIAL_INVALID"
    assert missing_credential.value.details == [
        {"field": "api_key", "reason": "Required by the selected provider"}
    ]

    view = await service.update(
        _principal("llm_configs.manage"),
        "tenant_test",
        reranker.id,
        RerankerConfigUpdateRequest(
            provider="aliyun_bailian",
            base_url=("https://workspace-test.cn-beijing.maas.aliyuncs.com/compatible-api/v1"),
            api_key=SecretStr("new-api-key"),
        ),
    )

    assert view.provider == "aliyun_bailian"
    assert view.model == "qwen3-rerank"
    assert view.base_url == (
        "https://workspace-test.cn-beijing.maas.aliyuncs.com/compatible-api/v1"
    )


@pytest.mark.asyncio
async def test_referenced_embedding_config_can_be_disabled_without_losing_its_record() -> None:
    embedding = EmbeddingConfig(
        id="embedding_test",
        tenant_id="tenant_test",
        name="Embedding",
        provider="openai_compatible",
        model="text-embedding-3-large",
        base_url="http://127.0.0.1:11434/v1",
        credential_envelope="v1.encrypted",
        embedding_dimension=1024,
        configuration_version=1,
        status="active",
    )
    reranker = RerankerConfig(
        id="reranker_test",
        tenant_id="tenant_test",
        name="Reranker",
        provider="parrot_http",
        model="bge-reranker-v2",
        base_url="http://127.0.0.1:11434/v1",
        credential_envelope="v1.encrypted",
        status="active",
    )
    database = cast(DatabaseManager, SimpleNamespace(set_tenant=AsyncMock()))
    embedding_service = EmbeddingConfigService(
        cast(
            AsyncSession,
            SimpleNamespace(
                add=Mock(),
                flush=AsyncMock(),
                scalar=AsyncMock(side_effect=(embedding, 1)),
            ),
        ),
        database,
        CredentialCipher(_key()),
        _settings(),
    )
    reranker_service = RerankerConfigService(
        cast(AsyncSession, SimpleNamespace(scalar=AsyncMock(side_effect=(reranker, "space_test")))),
        database,
        CredentialCipher(_key()),
        _settings(),
    )

    view = await embedding_service.update(
        _principal("llm_configs.manage"),
        "tenant_test",
        embedding.id,
        EmbeddingConfigUpdateRequest(provider="openai_compatible", status="disabled"),
    )
    with pytest.raises(AppError) as reranker_error:
        await reranker_service.update(
            _principal("llm_configs.manage"),
            "tenant_test",
            reranker.id,
            RerankerConfigUpdateRequest(provider="parrot_http", status="disabled"),
        )

    assert view.status == "disabled"
    assert view.reference_count == 1
    assert view.can_delete is False
    assert reranker_error.value.code == "RERANKER_CONFIG_IN_USE"
    assert reranker_error.value.status_code == 409


@pytest.mark.asyncio
async def test_merge_settings_reranker_cannot_be_disabled() -> None:
    reranker = RerankerConfig(
        id="reranker_test",
        tenant_id="tenant_test",
        name="Reranker",
        provider="parrot_http",
        model="bge-reranker-v2",
        base_url="http://127.0.0.1:11434/v1",
        credential_envelope="v1.encrypted",
        status="active",
    )
    service = RerankerConfigService(
        cast(
            AsyncSession,
            SimpleNamespace(
                scalar=AsyncMock(side_effect=(reranker, None, "tenant_test")),
                flush=AsyncMock(),
            ),
        ),
        cast(DatabaseManager, SimpleNamespace(set_tenant=AsyncMock())),
        CredentialCipher(_key()),
        _settings(),
    )

    with pytest.raises(AppError) as error:
        await service.update(
            _principal("llm_configs.manage"),
            "tenant_test",
            reranker.id,
            RerankerConfigUpdateRequest(provider="parrot_http", status="disabled"),
        )

    assert error.value.code == "RERANKER_CONFIG_IN_USE"
    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_referenced_embedding_endpoint_cannot_change_without_a_new_index_profile() -> None:
    embedding = EmbeddingConfig(
        id="embedding_test",
        tenant_id="tenant_test",
        name="Embedding",
        provider="openai_compatible",
        model="text-embedding-3-large",
        base_url="http://127.0.0.1:11434/v1",
        credential_envelope="v1.encrypted",
        embedding_dimension=1024,
        configuration_version=1,
        status="active",
    )
    service = EmbeddingConfigService(
        cast(
            AsyncSession,
            SimpleNamespace(scalar=AsyncMock(side_effect=(embedding, 1))),
        ),
        cast(DatabaseManager, SimpleNamespace(set_tenant=AsyncMock())),
        CredentialCipher(_key()),
        _settings(),
    )

    with pytest.raises(AppError) as error:
        await service.update(
            _principal("llm_configs.manage"),
            "tenant_test",
            embedding.id,
            EmbeddingConfigUpdateRequest(base_url="http://127.0.0.1:11434/other"),
        )

    assert error.value.code == "EMBEDDING_CONFIG_IDENTITY_IMMUTABLE"
    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_referenced_embedding_config_cannot_be_deleted() -> None:
    embedding = EmbeddingConfig(
        id="embedding_test",
        tenant_id="tenant_test",
        name="Embedding",
        provider="openai_compatible",
        model="text-embedding-3-large",
        base_url="http://127.0.0.1:11434/v1",
        credential_envelope="v1.encrypted",
        embedding_dimension=1024,
        configuration_version=1,
        status="disabled",
    )
    service = EmbeddingConfigService(
        cast(AsyncSession, SimpleNamespace(scalar=AsyncMock(side_effect=(embedding, 1)))),
        cast(DatabaseManager, SimpleNamespace(set_tenant=AsyncMock())),
        CredentialCipher(_key()),
        _settings(),
    )

    with pytest.raises(AppError) as error:
        await service.delete(_principal("llm_configs.manage"), "tenant_test", embedding.id)

    assert error.value.code == "EMBEDDING_CONFIG_IN_USE"
    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_embedding_config_with_historical_vector_records_cannot_be_deleted() -> None:
    embedding = EmbeddingConfig(
        id="embedding_test",
        tenant_id="tenant_test",
        name="Embedding",
        provider="openai_compatible",
        model="text-embedding-3-large",
        base_url="http://127.0.0.1:11434/v1",
        credential_envelope="v1.encrypted",
        embedding_dimension=1024,
        configuration_version=1,
        status="disabled",
    )
    service = EmbeddingConfigService(
        cast(
            AsyncSession,
            SimpleNamespace(scalar=AsyncMock(side_effect=(embedding, 0, "vector_job"))),
        ),
        cast(DatabaseManager, SimpleNamespace(set_tenant=AsyncMock())),
        CredentialCipher(_key()),
        _settings(),
    )

    with pytest.raises(AppError) as error:
        await service.delete(_principal("llm_configs.manage"), "tenant_test", embedding.id)

    assert error.value.code == "EMBEDDING_CONFIG_IN_USE"


def test_retrieval_policy_derives_processing_authorization_from_selected_configs() -> None:
    assert (
        KnowledgeSpaceCreateRequest(
            name="Knowledge", embedding_config_id="embedding_test"
        ).embedding_config_id
        == "embedding_test"
    )
    assert (
        KnowledgeSpaceRetrievalUpdateRequest(
            embedding_config_id="embedding_test",
            candidate_top_k=2,
            rerank_enabled=False,
            rerank_top_n=10,
        ).embedding_config_id
        == "embedding_test"
    )
    with pytest.raises(ValidationError, match="allow_external_processing"):
        KnowledgeSpaceCreateRequest.model_validate(
            {
                "name": "Knowledge",
                "embedding_config_id": "embedding_test",
                "allow_external_processing": True,
            }
        )
    with pytest.raises(ValidationError, match="rerank_top_n"):
        KnowledgeSpaceRetrievalUpdateRequest(
            embedding_config_id="embedding_test",
            candidate_top_k=6,
            rerank_enabled=True,
            reranker_config_id="reranker_test",
            rerank_top_n=7,
        )


def test_retrieval_model_endpoints_require_production_https_and_allowlists() -> None:
    with pytest.raises(AppError) as insecure:
        validate_model_endpoint(
            "http://models.example.test/v1",
            allowed_hosts=("models.example.test",),
            production=True,
            resource_label="Embedding",
        )
    with pytest.raises(AppError) as untrusted:
        validate_model_endpoint(
            "https://other.example.test/v1",
            allowed_hosts=("models.example.test",),
            production=True,
            resource_label="Reranker",
        )
    bailian = validate_model_endpoint(
        "https://workspace-test.cn-beijing.maas.aliyuncs.com/compatible-api/v1",
        allowed_hosts=(),
        trusted_host_suffixes=(".cn-beijing.maas.aliyuncs.com",),
        production=True,
        resource_label="Reranker",
    )
    with pytest.raises(AppError) as suffix_lookalike:
        validate_model_endpoint(
            "https://workspace-test.cn-beijing.maas.aliyuncs.com.example.test/v1",
            allowed_hosts=(),
            trusted_host_suffixes=(".cn-beijing.maas.aliyuncs.com",),
            production=True,
            resource_label="Reranker",
        )

    assert insecure.value.code == "MODEL_CONFIG_ENDPOINT_HTTPS_REQUIRED"
    assert untrusted.value.code == "MODEL_CONFIG_ENDPOINT_NOT_ALLOWED"
    assert bailian == ("https://workspace-test.cn-beijing.maas.aliyuncs.com/compatible-api/v1")
    assert suffix_lookalike.value.code == "MODEL_CONFIG_ENDPOINT_ALLOWLIST_REQUIRED"
