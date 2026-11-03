from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import cast

import httpx

from app.modules.model_providers.catalog import canonical_provider, provider_capability


class ProviderEmbeddingError(RuntimeError):
    def __init__(
        self, message: str, *, diagnostic_details: list[dict[str, str]] | None = None
    ) -> None:
        super().__init__(message)
        self.diagnostic_details = diagnostic_details or []


@dataclass(frozen=True)
class EmbeddingProviderProfile:
    provider: str
    model: str
    base_url: str
    api_key: str
    embedding_dimension: int


class ProviderEmbeddingClient:
    def __init__(
        self,
        profile: EmbeddingProviderProfile,
        *,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._profile = profile
        self._timeout = timeout_seconds
        self._transport = transport

    async def embed(self, values: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        if not values:
            return ()
        adapter = provider_capability(self._profile.provider, "embedding").adapter
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, transport=self._transport
            ) as client:
                if adapter == "openai_embedding":
                    result = await self._openai(client, values)
                elif adapter == "volcengine_multimodal_embedding":
                    result = await self._volcengine(client, values)
                else:
                    raise ProviderEmbeddingError("Embedding provider adapter is unavailable")
        except (httpx.HTTPError, ValueError, TypeError) as error:
            raise ProviderEmbeddingError("Embedding provider request failed") from error
        if len(result) != len(values):
            raise ProviderEmbeddingError(
                "Embedding provider returned an invalid count",
                diagnostic_details=[
                    {"field": "expected_response_count", "reason": str(len(values))},
                    {"field": "actual_response_count", "reason": str(len(result))},
                ],
            )
        actual_dimensions = sorted({len(item) for item in result})
        if actual_dimensions != [self._profile.embedding_dimension]:
            raise ProviderEmbeddingError(
                "Embedding provider returned an invalid dimension",
                diagnostic_details=[
                    {
                        "field": "expected_dimension",
                        "reason": str(self._profile.embedding_dimension),
                    },
                    {
                        "field": "actual_dimension",
                        "reason": ", ".join(str(value) for value in actual_dimensions),
                    },
                ],
            )
        return result

    async def _openai(
        self, client: httpx.AsyncClient, values: tuple[str, ...]
    ) -> tuple[tuple[float, ...], ...]:
        payload: dict[str, object] = {"model": self._profile.model, "input": list(values)}
        if canonical_provider(self._profile.provider) == "openai":
            payload["dimensions"] = self._profile.embedding_dimension
        response = await client.post(
            _append_path(self._profile.base_url, "/embeddings"),
            headers=self._headers(),
            json=payload,
        )
        response.raise_for_status()
        return _openai_embeddings(cast(object, response.json()), len(values))

    async def _volcengine(
        self, client: httpx.AsyncClient, values: tuple[str, ...]
    ) -> tuple[tuple[float, ...], ...]:
        endpoint = _append_path(self._profile.base_url, "/embeddings/multimodal")
        semaphore = asyncio.Semaphore(4)

        async def embed_one(value: str) -> tuple[float, ...]:
            async with semaphore:
                response = await client.post(
                    endpoint,
                    headers=self._headers(),
                    json={
                        "model": self._profile.model,
                        "encoding_format": "float",
                        "input": [{"type": "text", "text": value}],
                    },
                )
                response.raise_for_status()
                return _volcengine_embedding(cast(object, response.json()))

        return tuple(await asyncio.gather(*(embed_one(value) for value in values)))

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._profile.api_key}"}


def _append_path(base_url: str, path: str) -> str:
    normalized = base_url.rstrip("/")
    return normalized if normalized.endswith(path) else f"{normalized}{path}"


def _openai_embeddings(value: object, expected: int) -> tuple[tuple[float, ...], ...]:
    if not isinstance(value, dict):
        raise ValueError("OpenAI embedding response is invalid")
    payload = cast(dict[str, object], value)
    raw_data = payload.get("data")
    if not isinstance(raw_data, list):
        raise ValueError("OpenAI embedding response is invalid")
    raw_items = cast(list[object], raw_data)
    indexed: list[tuple[int, tuple[float, ...]]] = []
    for position, raw in enumerate(raw_items):
        if not isinstance(raw, dict):
            raise ValueError("OpenAI embedding response is invalid")
        item = cast(dict[str, object], raw)
        index = item.get("index", position)
        if not isinstance(index, int):
            raise ValueError("OpenAI embedding response is invalid")
        indexed.append((index, _vector(item.get("embedding"))))
    indexed.sort(key=lambda item: item[0])
    if len(indexed) != expected:
        raise ValueError("OpenAI embedding response count is invalid")
    return tuple(vector for _, vector in indexed)


def _volcengine_embedding(value: object) -> tuple[float, ...]:
    if not isinstance(value, dict):
        raise ValueError("Volcengine embedding response is invalid")
    payload = cast(dict[str, object], value)
    data = payload.get("data")
    if isinstance(data, list) and data:
        data = cast(list[object], data)[0]
    if not isinstance(data, dict):
        raise ValueError("Volcengine embedding response is invalid")
    output = cast(dict[str, object], data)
    raw = output.get("embedding")
    normalized: object = raw
    if isinstance(raw, list):
        raw_items = cast(list[object], raw)
        if len(raw_items) == 1 and isinstance(raw_items[0], list):
            normalized = cast(list[object], raw_items[0])
        else:
            normalized = raw_items
    return _vector(normalized)


def _vector(value: object) -> tuple[float, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError("Embedding vector is invalid")
    result: list[float] = []
    for item in cast(list[object], value):
        if not isinstance(item, int | float) or isinstance(item, bool):
            raise ValueError("Embedding vector is invalid")
        result.append(float(item))
    return tuple(result)
