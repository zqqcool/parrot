import json
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.infrastructure.db.session import DatabaseManager
from app.modules.iam.schemas import PrincipalContext
from app.modules.model_configs.connection_test import connection_test_failed
from app.modules.model_providers.catalog import (
    providers,
    selectable_provider_capability,
)
from app.modules.model_providers.embedding import (
    EmbeddingProviderProfile,
    ProviderEmbeddingClient,
    ProviderEmbeddingError,
)
from app.modules.model_providers.reranker import (
    ProviderRerankerClient,
    ProviderRerankerError,
    RerankerProviderProfile,
)
from app.modules.model_providers.reranker_credentials import RerankerProviderCredential
from app.modules.model_providers.service import ModelProviderCatalogService


def test_provider_catalog_exposes_bailian_reranker_without_ark_reranker() -> None:
    catalog = providers()

    assert [provider.key for provider in catalog] == [
        "openai",
        "volcengine_ark",
        "aliyun_bailian",
    ]
    assert [capability.kind for capability in catalog[0].capabilities] == ["llm", "embedding"]
    assert [capability.kind for capability in catalog[1].capabilities] == ["llm", "embedding"]
    assert catalog[1].capabilities[1].default_embedding_dimension == 2048
    assert [capability.kind for capability in catalog[2].capabilities] == ["reranker"]
    reranker = selectable_provider_capability("aliyun_bailian", "reranker")
    assert reranker.adapter == "aliyun_bailian_rerank"
    assert reranker.credential_type == "api_key"
    assert reranker.default_model == "qwen3-rerank"
    assert reranker.default_base_url is None
    assert reranker.trusted_host_suffixes == (".cn-beijing.maas.aliyuncs.com",)
    for unsupported_provider in ("openai", "volcengine_ark"):
        with pytest.raises(AppError) as unsupported:
            selectable_provider_capability(unsupported_provider, "reranker")
        assert unsupported.value.code == "MODEL_PROVIDER_UNSUPPORTED"


@pytest.mark.asyncio
async def test_provider_catalog_enforces_tenant_and_read_permission() -> None:
    database = cast(DatabaseManager, SimpleNamespace(set_tenant=AsyncMock()))
    service = ModelProviderCatalogService(cast(AsyncSession, SimpleNamespace()), database)
    principal = PrincipalContext(
        tenant_id="tenant_test",
        subject_id="user_test",
        username="admin",
        display_name="Admin",
        permissions=("llm_configs.read",),
        tenants=(),
        must_change_password=False,
        request_id="request_test",
    )

    result = await service.list(principal, "tenant_test")
    with pytest.raises(AppError) as invisible:
        await service.list(principal, "tenant_other")
    without_permission = principal.model_copy(update={"permissions": ()})
    with pytest.raises(AppError) as forbidden:
        await service.list(without_permission, "tenant_test")

    assert [provider.key for provider in result] == [
        "openai",
        "volcengine_ark",
        "aliyun_bailian",
    ]
    assert invisible.value.status_code == 404
    assert forbidden.value.status_code == 403


@pytest.mark.asyncio
async def test_openai_embedding_adapter_uses_standard_embeddings_contract() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [0.4, 0.5, 0.6]},
                    {"index": 0, "embedding": [0.1, 0.2, 0.3]},
                ]
            },
        )

    result = await ProviderEmbeddingClient(
        EmbeddingProviderProfile(
            provider="openai",
            model="text-embedding-3-small",
            base_url="https://api.openai.com/v1",
            api_key="secret",
            embedding_dimension=3,
        ),
        timeout_seconds=1,
        transport=httpx.MockTransport(handler),
    ).embed(("first", "second"))

    assert str(seen[0].url) == "https://api.openai.com/v1/embeddings"
    assert json.loads(seen[0].content) == {
        "model": "text-embedding-3-small",
        "input": ["first", "second"],
        "dimensions": 3,
    }
    assert result == ((0.1, 0.2, 0.3), (0.4, 0.5, 0.6))


@pytest.mark.asyncio
async def test_volcengine_embedding_adapter_uses_native_multimodal_contract() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"data": {"embedding": [0.1, 0.2, 0.3]}})

    result = await ProviderEmbeddingClient(
        EmbeddingProviderProfile(
            provider="volcengine_ark",
            model="doubao-embedding-vision-251215",
            base_url="https://ark.cn-beijing.volces.com/api/v3",
            api_key="secret",
            embedding_dimension=3,
        ),
        timeout_seconds=1,
        transport=httpx.MockTransport(handler),
    ).embed(("connection test",))

    assert str(seen[0].url) == ("https://ark.cn-beijing.volces.com/api/v3/embeddings/multimodal")
    assert json.loads(seen[0].content) == {
        "model": "doubao-embedding-vision-251215",
        "encoding_format": "float",
        "input": [{"type": "text", "text": "connection test"}],
    }
    assert result == ((0.1, 0.2, 0.3),)


@pytest.mark.asyncio
async def test_embedding_adapter_reports_expected_and_actual_dimensions() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"embedding": [0.1, 0.2, 0.3]}})

    with pytest.raises(ProviderEmbeddingError) as error:
        await ProviderEmbeddingClient(
            EmbeddingProviderProfile(
                provider="volcengine_ark",
                model="doubao-embedding-vision-251215",
                base_url="https://ark.cn-beijing.volces.com/api/v3",
                api_key="secret",
                embedding_dimension=2,
            ),
            timeout_seconds=1,
            transport=httpx.MockTransport(handler),
        ).embed(("connection test",))

    assert error.value.diagnostic_details == [
        {"field": "expected_dimension", "reason": "2"},
        {"field": "actual_dimension", "reason": "3"},
    ]


@pytest.mark.asyncio
async def test_bailian_reranker_adapter_uses_official_openai_compatible_extension() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "object": "list",
                "results": [
                    {"index": 2, "relevance_score": 0.92},
                    {"index": 0, "relevance_score": 0.71},
                ],
                "model": "qwen3-rerank",
                "id": "bailian_req_123",
            },
        )

    result = await ProviderRerankerClient(
        RerankerProviderProfile(
            provider="aliyun_bailian",
            model="qwen3-rerank",
            base_url=("https://workspace-test.cn-beijing.maas.aliyuncs.com/compatible-api/v1"),
            credential=RerankerProviderCredential(
                credential_type="api_key",
                api_key="test-api-key",
            ),
        ),
        timeout_seconds=1,
        transport=httpx.MockTransport(handler),
    ).rerank("connection test", ("first", "second", "third"), 2)

    assert str(seen[0].url) == (
        "https://workspace-test.cn-beijing.maas.aliyuncs.com/compatible-api/v1/reranks"
    )
    assert seen[0].headers["Authorization"] == "Bearer test-api-key"
    assert json.loads(seen[0].content) == {
        "model": "qwen3-rerank",
        "query": "connection test",
        "documents": ["first", "second", "third"],
        "top_n": 2,
    }
    assert [(item.index, item.score) for item in result] == [
        (2, 0.92),
        (0, 0.71),
    ]


@pytest.mark.asyncio
async def test_bailian_reranker_adapter_surfaces_safe_http_diagnostics() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={
                "code": "InvalidApiKey",
                "message": "Invalid API-key provided: sk-secret-value",
                "request_id": "bailian_req_123",
            },
        )

    client = ProviderRerankerClient(
        RerankerProviderProfile(
            provider="aliyun_bailian",
            model="qwen3-rerank",
            base_url=("https://workspace-test.cn-beijing.maas.aliyuncs.com/compatible-api/v1"),
            credential=RerankerProviderCredential(
                credential_type="api_key",
                api_key="test-api-key",
            ),
        ),
        timeout_seconds=1,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ProviderRerankerError) as provider_error:
        await client.rerank("query", ("document",), 1)

    failed = connection_test_failed(provider_error.value)
    assert failed.details == [
        {"field": "upstream_http_status", "reason": "401 Unauthorized"},
        {"field": "upstream_error_code", "reason": "InvalidApiKey"},
        {
            "field": "upstream_message",
            "reason": "Invalid API-key provided: [REDACTED]",
        },
        {"field": "upstream_request_id", "reason": "bailian_req_123"},
    ]
