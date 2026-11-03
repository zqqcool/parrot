from __future__ import annotations

from typing import cast

import httpx

from app.core.config import AppConfig, MemoryEmbeddingSection


class MemoryEmbeddingError(RuntimeError):
    pass


class OpenAiCompatibleEmbeddingClient:
    """Embedding client with an independent allowlist and explicit credential reference."""

    def __init__(
        self,
        settings: AppConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._section: MemoryEmbeddingSection = settings.memory.embedding
        self._credentials = settings.memory_credentials.values
        self._production = settings.app.environment == "prod"
        self._transport = transport

    async def embed(self, values: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        if not values:
            return ()
        url = self._url()
        try:
            async with httpx.AsyncClient(
                timeout=self._section.timeout_seconds,
                transport=self._transport,
            ) as client:
                payload = dict(self._section.extra_body)
                payload.update({"model": self._section.model, "input": list(values)})
                response = await client.post(
                    url,
                    headers={"Authorization": f"Bearer {self._credential()}"},
                    json=payload,
                )
                response.raise_for_status()
                raw = cast(object, response.json())
        except (httpx.HTTPError, ValueError) as error:
            raise MemoryEmbeddingError("Embedding service request failed") from error
        return _embeddings(raw, len(values))

    def validate(self) -> None:
        self._url()
        self._credential()

    def _url(self) -> str:
        if not self._section.base_url:
            raise MemoryEmbeddingError("Memory embedding endpoint is missing")
        try:
            base = httpx.URL(self._section.base_url)
        except ValueError as error:
            raise MemoryEmbeddingError("Memory embedding endpoint is invalid") from error
        if (
            base.scheme not in {"http", "https"}
            or not base.host
            or base.query
            or base.fragment
            or base.username
            or base.password
        ):
            raise MemoryEmbeddingError("Memory embedding endpoint is invalid")
        if self._production and base.scheme != "https":
            raise MemoryEmbeddingError("Production embedding endpoint must use HTTPS")
        allowed = {host.casefold() for host in self._section.allowed_hosts}
        if allowed and base.host.casefold() not in allowed:
            raise MemoryEmbeddingError("Memory embedding endpoint is not allowlisted")
        return f"{str(base).rstrip('/')}/embeddings"

    def _credential(self) -> str:
        reference = self._section.credential_ref
        value = self._credentials.get(reference or "")
        if not value:
            raise MemoryEmbeddingError("Memory embedding credential is unavailable")
        return value


def _embeddings(value: object, expected_count: int) -> tuple[tuple[float, ...], ...]:
    if not isinstance(value, dict):
        raise MemoryEmbeddingError("Embedding service response is invalid")
    payload = cast(dict[str, object], value)
    raw_data = payload.get("data")
    if not isinstance(raw_data, list):
        raise MemoryEmbeddingError("Embedding service response is invalid")
    data = cast(list[object], raw_data)
    if len(data) != expected_count:
        raise MemoryEmbeddingError("Embedding service response is invalid")
    vectors: list[tuple[float, ...]] = []
    for raw_item in data:
        if not isinstance(raw_item, dict):
            raise MemoryEmbeddingError("Embedding service response is invalid")
        item = cast(dict[str, object], raw_item)
        raw_embedding = item.get("embedding")
        if not isinstance(raw_embedding, list) or not raw_embedding:
            raise MemoryEmbeddingError("Embedding service response is invalid")
        embedding = cast(list[object], raw_embedding)
        if not all(
            isinstance(number, int | float) and not isinstance(number, bool) for number in embedding
        ):
            raise MemoryEmbeddingError("Embedding service response is invalid")
        vectors.append(tuple(float(cast(int | float, number)) for number in embedding))
    return tuple(vectors)
