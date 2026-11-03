from __future__ import annotations

from app.core.config import AppConfig
from app.core.errors import AppError
from app.infrastructure.credential_cipher import (
    CredentialCipher,
    CredentialCipherError,
    embedding_credential_context,
    reranker_credential_context,
)
from app.modules.embedding_configs.models import EmbeddingConfig
from app.modules.knowledge.embedding import KnowledgeEmbeddingError, KnowledgeEmbeddingPort
from app.modules.model_configs.endpoint_policy import validate_model_endpoint
from app.modules.model_providers.catalog import ModelKind, provider_capability
from app.modules.model_providers.embedding import (
    EmbeddingProviderProfile,
    ProviderEmbeddingClient,
    ProviderEmbeddingError,
)
from app.modules.model_providers.reranker import (
    ProviderRerankerClient,
    ProviderRerankResult,
    RerankerProviderProfile,
)
from app.modules.model_providers.reranker_credentials import (
    RerankerCredentialError,
    RerankerProviderCredential,
    decode_reranker_credential,
)
from app.modules.reranker_configs.models import RerankerConfig

RerankResult = ProviderRerankResult


class ConfiguredKnowledgeEmbedding(KnowledgeEmbeddingPort):
    def __init__(
        self,
        settings: AppConfig,
        cipher: CredentialCipher,
        config: EmbeddingConfig,
        *,
        timeout_seconds: float | None = None,
    ) -> None:
        self._config = config
        self._cipher = cipher
        self._url = _endpoint(
            settings,
            config.provider,
            "embedding",
            config.base_url,
            settings.knowledge.embedding.allowed_hosts,
            "Embedding",
        )
        self._timeout = (
            timeout_seconds
            if timeout_seconds is not None
            else settings.knowledge.embedding.timeout_seconds
        )

    async def embed(self, values: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        if not values:
            return ()
        try:
            return await ProviderEmbeddingClient(
                EmbeddingProviderProfile(
                    provider=self._config.provider,
                    model=self._config.model,
                    base_url=self._url,
                    api_key=self._credential(),
                    embedding_dimension=self._config.embedding_dimension,
                ),
                timeout_seconds=self._timeout,
            ).embed(values)
        except ProviderEmbeddingError as error:
            raise KnowledgeEmbeddingError("Knowledge embedding request failed") from error

    def _credential(self) -> str:
        if not self._config.credential_envelope:
            raise KnowledgeEmbeddingError("Knowledge embedding credential is unavailable")
        try:
            return self._cipher.decrypt(
                self._config.credential_envelope,
                context=embedding_credential_context(self._config.id),
            )
        except CredentialCipherError as error:
            raise KnowledgeEmbeddingError(
                "Knowledge embedding credential is unavailable"
            ) from error


class ConfiguredReranker:
    """Provider-independent runtime facade for tenant-owned reranking configs."""

    def __init__(
        self,
        settings: AppConfig,
        cipher: CredentialCipher,
        config: RerankerConfig,
        *,
        timeout_seconds: float | None = None,
    ) -> None:
        self._config = config
        self._cipher = cipher
        self._url = _endpoint(
            settings,
            config.provider,
            "reranker",
            config.base_url,
            settings.knowledge.reranker.allowed_hosts,
            "Reranker",
        )
        self._timeout = (
            timeout_seconds
            if timeout_seconds is not None
            else settings.knowledge.reranker.timeout_seconds
        )

    async def rerank(
        self, query: str, documents: tuple[str, ...], top_n: int
    ) -> tuple[RerankResult, ...]:
        if not documents:
            return ()
        return await ProviderRerankerClient(
            RerankerProviderProfile(
                provider=self._config.provider,
                model=self._config.model,
                base_url=self._url,
                credential=self._credential(),
            ),
            timeout_seconds=self._timeout,
        ).rerank(query, documents, top_n)

    def _credential(self) -> RerankerProviderCredential:
        if not self._config.credential_envelope:
            raise RuntimeError("Knowledge reranker credential is unavailable")
        try:
            decrypted = self._cipher.decrypt(
                self._config.credential_envelope,
                context=reranker_credential_context(self._config.id),
            )
            credential_type = provider_capability(self._config.provider, "reranker").credential_type
            return decode_reranker_credential(decrypted, credential_type)
        except (CredentialCipherError, RerankerCredentialError) as error:
            raise RuntimeError("Knowledge reranker credential is unavailable") from error


def _endpoint(
    settings: AppConfig,
    provider: str,
    kind: ModelKind,
    value: str,
    allowed_hosts: tuple[str, ...],
    label: str,
) -> str:
    try:
        capability = provider_capability(provider, kind)
        return validate_model_endpoint(
            value,
            allowed_hosts=allowed_hosts,
            trusted_hosts=capability.trusted_hosts,
            trusted_host_suffixes=capability.trusted_host_suffixes,
            production=settings.app.environment == "prod",
            resource_label=label,
        )
    except AppError as error:
        raise RuntimeError(f"{label} endpoint is unavailable") from error
