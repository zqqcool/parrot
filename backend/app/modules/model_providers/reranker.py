from __future__ import annotations

from dataclasses import dataclass
from typing import cast

import httpx

from app.modules.model_providers.catalog import provider_capability
from app.modules.model_providers.reranker_credentials import RerankerProviderCredential


@dataclass(frozen=True)
class ProviderRerankResult:
    index: int
    score: float


@dataclass(frozen=True)
class RerankerProviderProfile:
    provider: str
    model: str
    base_url: str
    credential: RerankerProviderCredential


class ProviderRerankerError(RuntimeError):
    def __init__(self, message: str, *, diagnostic_details: list[dict[str, str]] | None = None):
        self.diagnostic_details = diagnostic_details or []
        super().__init__(message)


class ProviderRerankerClient:
    def __init__(
        self,
        profile: RerankerProviderProfile,
        *,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._profile = profile
        self._timeout = timeout_seconds
        self._transport = transport

    async def rerank(
        self, query: str, documents: tuple[str, ...], top_n: int
    ) -> tuple[ProviderRerankResult, ...]:
        if not documents:
            return ()
        adapter = provider_capability(self._profile.provider, "reranker").adapter
        if adapter == "parrot_rerank":
            return await self._http("/rerank", query, documents, top_n)
        if adapter == "aliyun_bailian_rerank":
            return await self._http("/reranks", query, documents, top_n)
        raise ProviderRerankerError("Reranker provider adapter is unavailable")

    async def _http(
        self,
        path: str,
        query: str,
        documents: tuple[str, ...],
        top_n: int,
    ) -> tuple[ProviderRerankResult, ...]:
        api_key = self._profile.credential.api_key
        if not api_key:
            raise ProviderRerankerError("Reranker provider credential is unavailable")
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, transport=self._transport
            ) as client:
                response = await client.post(
                    _append_path(self._profile.base_url, path),
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": self._profile.model,
                        "query": query,
                        "documents": list(documents),
                        "top_n": top_n,
                    },
                )
                response.raise_for_status()
                raw = cast(object, response.json())
        except (httpx.HTTPError, ValueError) as error:
            raise ProviderRerankerError("Reranker provider request failed") from error
        return _http_results(raw, len(documents), top_n)


def _append_path(base_url: str, path: str) -> str:
    normalized = base_url.rstrip("/")
    return normalized if normalized.endswith(path) else f"{normalized}{path}"


def _http_results(
    value: object, document_count: int, top_n: int
) -> tuple[ProviderRerankResult, ...]:
    if not isinstance(value, dict):
        raise ProviderRerankerError("Reranker provider response is invalid")
    payload = cast(dict[str, object], value)
    raw_results = payload.get("results")
    if not isinstance(raw_results, list):
        raise ProviderRerankerError("Reranker provider response is invalid")
    results: list[ProviderRerankResult] = []
    for raw in cast(list[object], raw_results):
        item = cast(dict[str, object], raw) if isinstance(raw, dict) else {}
        index = item.get("index")
        score = item.get("relevance_score", item.get("score"))
        if not _valid_result(index, score, document_count):
            raise ProviderRerankerError("Reranker provider response is invalid")
        normalized_index = cast(int, index)
        if all(result.index != normalized_index for result in results):
            results.append(
                ProviderRerankResult(
                    index=normalized_index,
                    score=float(cast(float, score)),
                )
            )
    results.sort(key=lambda item: (-item.score, item.index))
    return tuple(results[:top_n])


def _valid_result(index: object, score: object, document_count: int) -> bool:
    return (
        isinstance(index, int)
        and not isinstance(index, bool)
        and 0 <= index < document_count
        and isinstance(score, int | float)
        and not isinstance(score, bool)
        and 0 <= float(score) <= 1
    )
