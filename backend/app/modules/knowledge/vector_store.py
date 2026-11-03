from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Protocol, cast

from pymilvus import DataType, MilvusClient  # pyright: ignore[reportMissingTypeStubs]

from app.core.config import AppConfig, knowledge_vector_runtime_issue


@dataclass(frozen=True)
class KnowledgeVector:
    id: str
    tenant_id: str
    space_id: str
    document_version_id: str
    chunk_id: str
    vector: tuple[float, ...]


@dataclass(frozen=True)
class KnowledgeVectorSearchScope:
    tenant_id: str
    space_ids: tuple[str, ...]


@dataclass(frozen=True)
class KnowledgeVectorHit:
    chunk_id: str
    score: float


class KnowledgeVectorStore(Protocol):
    async def upsert(self, vectors: tuple[KnowledgeVector, ...]) -> None: ...

    async def delete(self, vector_ids: tuple[str, ...]) -> None: ...

    async def search(
        self,
        vector: tuple[float, ...],
        scope: KnowledgeVectorSearchScope,
        limit: int,
    ) -> tuple[str, ...]: ...


class MilvusKnowledgeVectorStore:
    """Milvus adapter hidden behind the stable knowledge-vector port."""

    def __init__(
        self,
        settings: AppConfig,
        *,
        collection: str | None = None,
        embedding_dimension: int | None = None,
    ) -> None:
        section = settings.knowledge.vector
        if issue := knowledge_vector_runtime_issue(settings):
            raise ValueError(issue)
        assert section.uri is not None
        token = settings.knowledge_credentials.values.get(section.token_ref or "")
        if not token:
            raise ValueError("Knowledge vector credential is unavailable")
        self._client: Any = MilvusClient(uri=section.uri, token=token, db_name=section.database)
        self._collection = collection or section.collection
        self._dimension = embedding_dimension or section.embedding_dimension
        self._metric = section.metric_type

    async def upsert(self, vectors: tuple[KnowledgeVector, ...]) -> None:
        if not vectors:
            return
        self._validate_dimensions(vectors)
        await asyncio.to_thread(self._ensure_collection)
        await asyncio.to_thread(
            self._client.upsert,
            self._collection,
            [_payload(item) for item in vectors],
        )

    async def delete(self, vector_ids: tuple[str, ...]) -> None:
        if not vector_ids:
            return
        exists = await asyncio.to_thread(self._client.has_collection, self._collection)
        if exists:
            await asyncio.to_thread(self._client.delete, self._collection, list(vector_ids))

    async def search(
        self,
        vector: tuple[float, ...],
        scope: KnowledgeVectorSearchScope,
        limit: int,
    ) -> tuple[str, ...]:
        return tuple(item.chunk_id for item in await self.search_scored(vector, scope, limit))

    async def search_scored(
        self,
        vector: tuple[float, ...],
        scope: KnowledgeVectorSearchScope,
        limit: int,
    ) -> tuple[KnowledgeVectorHit, ...]:
        if not scope.space_ids:
            return ()
        if len(vector) != self._dimension:
            raise ValueError("Knowledge embedding dimension does not match vector collection")
        exists = await asyncio.to_thread(self._client.has_collection, self._collection)
        if not exists:
            return ()
        result = await asyncio.to_thread(
            self._client.search,
            self._collection,
            [list(vector)],
            knowledge_vector_scope_filter(scope),
            limit,
            ["chunk_id"],
        )
        return _hits(result)

    def _validate_dimensions(self, vectors: tuple[KnowledgeVector, ...]) -> None:
        if any(len(item.vector) != self._dimension for item in vectors):
            raise ValueError("Knowledge embedding dimension does not match vector collection")

    def _ensure_collection(self) -> None:
        if self._client.has_collection(self._collection):
            return
        schema = self._client.create_schema(auto_id=False, enable_dynamic_field=False)
        schema.add_field("id", DataType.VARCHAR, max_length=191, is_primary=True)
        schema.add_field("vector", DataType.FLOAT_VECTOR, dim=self._dimension)
        schema.add_field("tenant_id", DataType.VARCHAR, max_length=64)
        schema.add_field("space_id", DataType.VARCHAR, max_length=64)
        schema.add_field("document_version_id", DataType.VARCHAR, max_length=64)
        schema.add_field("chunk_id", DataType.VARCHAR, max_length=64)
        indexes = self._client.prepare_index_params()
        indexes.add_index("vector", index_type="AUTOINDEX", metric_type=self._metric)
        self._client.create_collection(self._collection, schema=schema, index_params=indexes)


def _payload(value: KnowledgeVector) -> dict[str, object]:
    return {
        "id": value.id,
        "vector": list(value.vector),
        "tenant_id": value.tenant_id,
        "space_id": value.space_id,
        "document_version_id": value.document_version_id,
        "chunk_id": value.chunk_id,
    }


def knowledge_vector_scope_filter(scope: KnowledgeVectorSearchScope) -> str:
    spaces = " or ".join(f"space_id == {_literal(item)}" for item in scope.space_ids)
    return f"tenant_id == {_literal(scope.tenant_id)} and ({spaces})"


def _literal(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _chunk_ids(value: object) -> tuple[str, ...]:  # pyright: ignore[reportUnusedFunction]
    return tuple(item.chunk_id for item in _hits(value))


def _hits(value: object) -> tuple[KnowledgeVectorHit, ...]:
    if not isinstance(value, list) or not value or not isinstance(value[0], list):
        return ()
    hits: list[KnowledgeVectorHit] = []
    for raw in cast(list[object], value[0]):
        if not isinstance(raw, dict):
            continue
        hit = cast(dict[str, object], raw)
        entity = hit.get("entity")
        chunk_id = (
            cast(dict[str, object], entity).get("chunk_id")
            if isinstance(entity, dict)
            else hit.get("chunk_id")
        )
        score = hit.get("distance")
        if (
            isinstance(chunk_id, str)
            and chunk_id
            and isinstance(score, int | float)
            and not isinstance(score, bool)
            and all(item.chunk_id != chunk_id for item in hits)
        ):
            hits.append(KnowledgeVectorHit(chunk_id=chunk_id, score=float(score)))
    return tuple(hits)
