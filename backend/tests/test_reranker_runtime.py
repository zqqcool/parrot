import base64
from pathlib import Path

import pytest

import app.modules.knowledge.retrieval_clients as retrieval_clients_module
from app.core.config import load_app_config
from app.infrastructure.credential_cipher import CredentialCipher, reranker_credential_context
from app.modules.knowledge.retrieval_clients import ConfiguredReranker
from app.modules.model_providers.reranker import RerankerProviderProfile
from app.modules.model_providers.reranker_credentials import (
    build_reranker_credential,
    encode_reranker_credential,
)
from app.modules.reranker_configs.models import RerankerConfig

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.asyncio
async def test_configured_reranker_passes_decrypted_api_key_to_provider_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cipher = CredentialCipher(base64.urlsafe_b64encode(b"0" * 32).decode().rstrip("="))
    config_id = "reranker_test"
    credential = build_reranker_credential("api_key", api_key="test-api-key")
    config = RerankerConfig(
        id=config_id,
        tenant_id="tenant_test",
        name="Bailian reranker",
        provider="aliyun_bailian",
        model="qwen3-rerank",
        base_url=("https://workspace-test.cn-beijing.maas.aliyuncs.com/compatible-api/v1"),
        credential_envelope=cipher.encrypt(
            encode_reranker_credential(credential),
            context=reranker_credential_context(config_id),
        ),
        status="active",
    )
    seen: list[RerankerProviderProfile] = []

    class FakeProviderClient:
        def __init__(self, profile: RerankerProviderProfile, **_kwargs: object) -> None:
            seen.append(profile)

        async def rerank(self, *_args: object) -> tuple[object, ...]:
            return ()

    monkeypatch.setattr(retrieval_clients_module, "ProviderRerankerClient", FakeProviderClient)

    runtime = ConfiguredReranker(load_app_config(ROOT / "config" / "dev.toml"), cipher, config)
    result = await runtime.rerank("query", ("document",), 1)

    assert result == ()
    assert seen[0].provider == "aliyun_bailian"
    assert seen[0].credential.api_key == "test-api-key"
