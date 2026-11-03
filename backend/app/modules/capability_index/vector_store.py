from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Protocol, cast

from pymilvus import DataType, MilvusClient  # pyright: ignore[reportMissingTypeStubs]

from app.core.config import AppConfig


@dataclass(frozen=True)
class CapabilityVector:
    id: str
    tenant_id: str
    source_kind: str
    source_id: str
    owner_id: str
    vector: tuple[float, ...]


@dataclass(frozen=True)
class CapabilityVectorHit:
    source_id: str
    score: float


class CapabilityVectorStore(Protocol):
    async def upsert(self, vectors: tuple[CapabilityVector, ...]) -> None: ...

    async def delete(self, vector_ids: tuple[str, ...]) -> None: ...

    async def delete_owner(self, tenant_id: str, owner_id: str) -> None: ...

    async def search(
        self, vector: tuple[float, ...], tenant_id: str, source_ids: tuple[str, ...], limit: int
    ) -> tuple[CapabilityVectorHit, ...]: ...


class MilvusCapabilityVectorStore:
    """System-configured Milvus collection dedicated to runtime capabilities."""

    def __init__(self, settings: AppConfig) -> None:
        section = settings.capability_index.vector
        if not settings.capability_index.enabled or not section.uri:
            raise ValueError("Capability indexing is disabled or its vector URI is unavailable")
        token = settings.memory_credentials.values.get(section.token_ref or "")
        if not token:
            raise ValueError("Capability vector credential is unavailable")
        self._client: Any = MilvusClient(uri=section.uri, token=token, db_name=section.database)
        self.collection = section.collection
        self._dimension = section.embedding_dimension
        self._metric = section.metric_type

    async def upsert(self, vectors: tuple[CapabilityVector, ...]) -> None:
        if not vectors:
            return
        if any(len(item.vector) != self._dimension for item in vectors):
            raise ValueError("Capability embedding dimension does not match vector collection")
        await asyncio.to_thread(self._ensure_collection)
        await asyncio.to_thread(
            self._client.upsert, self.collection, [_payload(item) for item in vectors]
        )

    async def delete(self, vector_ids: tuple[str, ...]) -> None:
        if vector_ids and await asyncio.to_thread(self._client.has_collection, self.collection):
            await asyncio.to_thread(self._client.delete, self.collection, list(vector_ids))

    async def delete_owner(self, tenant_id: str, owner_id: str) -> None:
        if await asyncio.to_thread(self._client.has_collection, self.collection):
            await asyncio.to_thread(
                self._client.delete,
                self.collection,
                _owner_filter(tenant_id, owner_id),
            )

    async def search(
        self, vector: tuple[float, ...], tenant_id: str, source_ids: tuple[str, ...], limit: int
    ) -> tuple[CapabilityVectorHit, ...]:
        if not source_ids or len(vector) != self._dimension:
            return ()
        if not await asyncio.to_thread(self._client.has_collection, self.collection):
            return ()
        result = await asyncio.to_thread(
            self._client.search,
            self.collection,
            [list(vector)],
            _scope_filter(tenant_id, source_ids),
            limit,
            ["source_id"],
        )
        return _hits(result)

    def _ensure_collection(self) -> None:
        if self._client.has_collection(self.collection):
            return
        schema = self._client.create_schema(auto_id=False, enable_dynamic_field=False)
        schema.add_field("id", DataType.VARCHAR, max_length=191, is_primary=True)
        schema.add_field("vector", DataType.FLOAT_VECTOR, dim=self._dimension)
        schema.add_field("tenant_id", DataType.VARCHAR, max_length=64)
        schema.add_field("source_kind", DataType.VARCHAR, max_length=16)
        schema.add_field("source_id", DataType.VARCHAR, max_length=191)
        schema.add_field("owner_id", DataType.VARCHAR, max_length=64)
        indexes = self._client.prepare_index_params()
        indexes.add_index("vector", index_type="AUTOINDEX", metric_type=self._metric)
        self._client.create_collection(self.collection, schema=schema, index_params=indexes)


def _payload(item: CapabilityVector) -> dict[str, object]:
    return {
        "id": item.id,
        "vector": list(item.vector),
        "tenant_id": item.tenant_id,
        "source_kind": item.source_kind,
        "source_id": item.source_id,
        "owner_id": item.owner_id,
    }


def _scope_filter(tenant_id: str, source_ids: tuple[str, ...]) -> str:
    sources = " or ".join(f"source_id == {json.dumps(item)}" for item in source_ids)
    return f"tenant_id == {json.dumps(tenant_id)} and ({sources})"


def _owner_filter(tenant_id: str, owner_id: str) -> str:
    return f"tenant_id == {json.dumps(tenant_id)} and owner_id == {json.dumps(owner_id)}"


def _hits(value: object) -> tuple[CapabilityVectorHit, ...]:
    if not isinstance(value, list) or not value or not isinstance(value[0], list):
        return ()
    hits: list[CapabilityVectorHit] = []
    for raw in cast(list[object], value[0]):
        if not isinstance(raw, dict):
            continue
        item = cast(dict[str, object], raw)
        entity = item.get("entity")
        source_id = (
            cast(dict[str, object], entity).get("source_id") if isinstance(entity, dict) else None
        )
        score = item.get("distance")
        if (
            isinstance(source_id, str)
            and isinstance(score, int | float)
            and source_id not in {hit.source_id for hit in hits}
        ):
            hits.append(CapabilityVectorHit(source_id, float(score)))
    return tuple(hits)
