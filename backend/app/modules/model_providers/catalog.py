from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from starlette import status

from app.core.errors import AppError

ModelKind = Literal["llm", "embedding", "reranker"]
CredentialType = Literal["api_key", "access_key_pair"]


@dataclass(frozen=True)
class ProviderCapability:
    kind: ModelKind
    description: str
    adapter: str
    credential_type: CredentialType = "api_key"
    default_base_url: str | None = None
    default_model: str | None = None
    default_embedding_dimension: int | None = None
    base_url_placeholder: str | None = None
    model_placeholder: str | None = None
    trusted_hosts: tuple[str, ...] = ()
    trusted_host_suffixes: tuple[str, ...] = ()


@dataclass(frozen=True)
class ModelProvider:
    key: str
    name: str
    capabilities: tuple[ProviderCapability, ...]


_PROVIDERS = (
    ModelProvider(
        key="openai",
        name="OpenAI",
        capabilities=(
            ProviderCapability(
                kind="llm",
                description="使用 OpenAI Chat Completions 协议。",
                adapter="openai_chat",
                default_base_url="https://api.openai.com/v1",
                model_placeholder="例如：gpt-4.1-mini",
                trusted_hosts=("api.openai.com",),
            ),
            ProviderCapability(
                kind="embedding",
                description="使用 OpenAI Embeddings 接口。",
                adapter="openai_embedding",
                default_base_url="https://api.openai.com/v1",
                default_model="text-embedding-3-large",
                default_embedding_dimension=3072,
                trusted_hosts=("api.openai.com",),
            ),
        ),
    ),
    ModelProvider(
        key="volcengine_ark",
        name="火山方舟（豆包）",
        capabilities=(
            ProviderCapability(
                kind="llm",
                description="通过方舟 OpenAI 兼容的 Chat Completions 接口调用。",
                adapter="openai_chat",
                default_base_url="https://ark.cn-beijing.volces.com/api/v3",
                default_model="doubao-seed-2-0-mini-260215",
                trusted_hosts=("ark.cn-beijing.volces.com",),
            ),
            ProviderCapability(
                kind="embedding",
                description="通过方舟原生图文向量化接口调用，不使用 OpenAI /embeddings。",
                adapter="volcengine_multimodal_embedding",
                default_base_url="https://ark.cn-beijing.volces.com/api/v3",
                default_model="doubao-embedding-vision-251215",
                default_embedding_dimension=2048,
                trusted_hosts=("ark.cn-beijing.volces.com",),
            ),
        ),
    ),
    ModelProvider(
        key="aliyun_bailian",
        name="阿里云百炼",
        capabilities=(
            ProviderCapability(
                kind="reranker",
                description=(
                    "通过百炼 qwen3-rerank 的 OpenAI 兼容扩展接口调用；服务地址需包含业务空间 ID。"
                ),
                adapter="aliyun_bailian_rerank",
                default_model="qwen3-rerank",
                base_url_placeholder=(
                    "例如：https://{业务空间ID}.cn-beijing.maas.aliyuncs.com/compatible-api/v1"
                ),
                trusted_host_suffixes=(".cn-beijing.maas.aliyuncs.com",),
            ),
        ),
    ),
)

_PROVIDER_BY_KEY = {provider.key: provider for provider in _PROVIDERS}
_LEGACY_PROVIDER_BY_KEY = {
    "openai_compatible": ModelProvider(
        key="openai_compatible",
        name="旧版 OpenAI 兼容配置",
        capabilities=(
            ProviderCapability(kind="llm", description="Legacy", adapter="openai_chat"),
            ProviderCapability(kind="embedding", description="Legacy", adapter="openai_embedding"),
        ),
    ),
    "parrot_http": ModelProvider(
        key="parrot_http",
        name="旧版自定义重排序配置",
        capabilities=(
            ProviderCapability(kind="reranker", description="Legacy", adapter="parrot_rerank"),
        ),
    ),
}
_ALIASES = {"openai-compatible": "openai_compatible"}


def providers() -> tuple[ModelProvider, ...]:
    return _PROVIDERS


def canonical_provider(value: str) -> str:
    normalized = value.strip().casefold()
    return _ALIASES.get(normalized, normalized)


def provider_capability(
    provider: str, kind: ModelKind, *, allow_legacy_llm: bool = False
) -> ProviderCapability:
    canonical = canonical_provider(provider)
    definition = _PROVIDER_BY_KEY.get(canonical) or _LEGACY_PROVIDER_BY_KEY.get(canonical)
    if definition is not None:
        for capability in definition.capabilities:
            if capability.kind == kind:
                return capability
    if allow_legacy_llm and kind == "llm":
        return _LEGACY_PROVIDER_BY_KEY["openai_compatible"].capabilities[0]
    raise AppError(
        "MODEL_PROVIDER_UNSUPPORTED",
        "Model provider does not support this capability",
        status.HTTP_422_UNPROCESSABLE_CONTENT,
    )


def selectable_provider_capability(provider: str, kind: ModelKind) -> ProviderCapability:
    canonical = canonical_provider(provider)
    definition = _PROVIDER_BY_KEY.get(canonical)
    if definition is not None:
        for capability in definition.capabilities:
            if capability.kind == kind:
                return capability
    raise AppError(
        "MODEL_PROVIDER_UNSUPPORTED",
        "Model provider does not support this capability",
        status.HTTP_422_UNPROCESSABLE_CONTENT,
    )
