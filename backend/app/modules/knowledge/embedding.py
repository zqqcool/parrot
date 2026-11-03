from __future__ import annotations

from typing import Protocol, cast

import httpx

from app.core.config import AppConfig, KnowledgeEmbeddingSection


class KnowledgeEmbeddingError(RuntimeError):
    pass


class KnowledgeEmbeddingPort(Protocol):
    async def embed(self, values: tuple[str, ...]) -> tuple[tuple[float, ...], ...]: ...


class OpenAiCompatibleKnowledgeEmbedding:
    """Knowledge-owned embedding adapter with explicit host and credential policy."""

    def __init__(
        self,
        settings: AppConfig,
        *,
        section: KnowledgeEmbeddingSection | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._section = section or settings.knowledge.embedding
        self._credentials = (
            settings.memory_credentials.values
            if section is not None
            else settings.knowledge_credentials.values
        )
        self._production = settings.app.environment == "prod"
        self._transport = transport

    async def embed(self, values: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        if not values:
            return ()
        try:
            async with httpx.AsyncClient(
                timeout=self._section.timeout_seconds,
                transport=self._transport,
            ) as client:
                response = await client.post(
                    self._url(),
                    headers={"Authorization": f"Bearer {self._credential()}"},
                    json={"model": self._section.model, "input": list(values)},
                )
                response.raise_for_status()
                raw = cast(object, response.json())
        except (httpx.HTTPError, ValueError) as error:
            raise KnowledgeEmbeddingError("Knowledge embedding request failed") from error
        return parse_embeddings(raw, len(values))

    def validate(self) -> None:
        self._url()
        self._credential()

    def _url(self) -> str:
        if not self._section.base_url:
            raise KnowledgeEmbeddingError("Knowledge embedding endpoint is missing")
        try:
            base = httpx.URL(self._section.base_url)
        except ValueError as error:
            raise KnowledgeEmbeddingError("Knowledge embedding endpoint is invalid") from error
        if (
            base.scheme not in {"http", "https"}
            or not base.host
            or base.query
            or base.fragment
            or base.username
            or base.password
        ):
            raise KnowledgeEmbeddingError("Knowledge embedding endpoint is invalid")
        if self._production and base.scheme != "https":
            raise KnowledgeEmbeddingError("Production knowledge embedding must use HTTPS")
        allowed = {host.casefold() for host in self._section.allowed_hosts}
        if allowed and base.host.casefold() not in allowed:
            raise KnowledgeEmbeddingError("Knowledge embedding endpoint is not allowlisted")
        return f"{str(base).rstrip('/')}/embeddings"

    def _credential(self) -> str:
        value = self._credentials.get(self._section.credential_ref or "")
        if not value:
            raise KnowledgeEmbeddingError("Knowledge embedding credential is unavailable")
        return value


def parse_embeddings(value: object, expected_count: int) -> tuple[tuple[float, ...], ...]:
    if not isinstance(value, dict):
        raise KnowledgeEmbeddingError("Knowledge embedding response is invalid")
    raw_data = cast(dict[str, object], value).get("data")
    if not isinstance(raw_data, list):
        raise KnowledgeEmbeddingError("Knowledge embedding response is invalid")
    data = cast(list[object], raw_data)
    if len(data) != expected_count:
        raise KnowledgeEmbeddingError("Knowledge embedding response is invalid")
    vectors: list[tuple[float, ...]] = []
    for raw_item in data:
        if not isinstance(raw_item, dict):
            raise KnowledgeEmbeddingError("Knowledge embedding response is invalid")
        raw_embedding = cast(dict[str, object], raw_item).get("embedding")
        if not isinstance(raw_embedding, list) or not raw_embedding:
            raise KnowledgeEmbeddingError("Knowledge embedding response is invalid")
        embedding = cast(list[object], raw_embedding)
        if not all(
            isinstance(number, int | float) and not isinstance(number, bool) for number in embedding
        ):
            raise KnowledgeEmbeddingError("Knowledge embedding response is invalid")
        vectors.append(tuple(float(cast(int | float, number)) for number in embedding))
    return tuple(vectors)
