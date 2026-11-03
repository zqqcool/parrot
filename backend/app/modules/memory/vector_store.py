from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Protocol, cast

from pymilvus import DataType, MilvusClient  # pyright: ignore[reportMissingTypeStubs]

from app.core.config import AppConfig


@dataclass(frozen=True)
class MemoryVector:
    id: str
    memory_id: str
    chunk_index: int
    vector: tuple[float, ...]
    tenant_id: str
    agent_id: str | None
    scope_type: str
    scope_id: str


class MemoryVectorStore(Protocol):
    async def upsert(self, vectors: tuple[MemoryVector, ...]) -> None: ...

    async def delete(self, vector_ids: tuple[str, ...]) -> None: ...

    async def search(
        self, vector: tuple[float, ...], context: MemoryVectorSearchContext, limit: int
    ) -> tuple[str, ...]: ...


@dataclass(frozen=True)
class MemoryVectorSearchContext:
    tenant_id: str
    agent_id: str
    actor_id: str
    conversation_id: str | None


class MilvusMemoryVectorStore:
    """Synchronous Milvus operations isolated behind an async tenant-filtered port."""

    def __init__(self, settings: AppConfig) -> None:
        section = settings.memory.vector
        if not section.enabled or not section.uri:
            raise ValueError("Memory vector store is not configured")
        token = settings.memory_credentials.values.get(section.token_ref or "")
        if not token:
            raise ValueError("Memory vector credential is unavailable")
        self._client: Any = MilvusClient(uri=section.uri, token=token, db_name=section.database)
        self._collection = section.collection
        self._dimension = section.embedding_dimension
        self._metric = section.metric_type

    async def upsert(self, vectors: tuple[MemoryVector, ...]) -> None:
        if not vectors:
            return
        self._validate_dimensions(vectors)
        await asyncio.to_thread(self._ensure_collection)
        await asyncio.to_thread(
            self._client.upsert,
            self._collection,
            [_vector_payload(item) for item in vectors],
        )

    async def delete(self, vector_ids: tuple[str, ...]) -> None:
        if not vector_ids:
            return
        exists = await asyncio.to_thread(self._client.has_collection, self._collection)
        if exists:
            await asyncio.to_thread(self._client.delete, self._collection, list(vector_ids))

    async def search(
        self, vector: tuple[float, ...], context: MemoryVectorSearchContext, limit: int
    ) -> tuple[str, ...]:
        if len(vector) != self._dimension:
            raise ValueError("Memory embedding dimension does not match vector collection")
        exists = await asyncio.to_thread(self._client.has_collection, self._collection)
        if not exists:
            return ()
        result = await asyncio.to_thread(
            self._client.search,
            self._collection,
            [list(vector)],
            memory_scope_filter(context),
            limit,
            ["memory_id"],
        )
        return _memory_ids(result)

    def _validate_dimensions(self, vectors: tuple[MemoryVector, ...]) -> None:
        if any(len(item.vector) != self._dimension for item in vectors):
            raise ValueError("Memory embedding dimension does not match vector collection")

    def _ensure_collection(self) -> None:
        if self._client.has_collection(self._collection):
            return
        schema = self._client.create_schema(auto_id=False, enable_dynamic_field=False)
        schema.add_field("id", DataType.VARCHAR, max_length=191, is_primary=True)
        schema.add_field("vector", DataType.FLOAT_VECTOR, dim=self._dimension)
        schema.add_field("tenant_id", DataType.VARCHAR, max_length=64)
        schema.add_field("agent_id", DataType.VARCHAR, max_length=64)
        schema.add_field("scope_type", DataType.VARCHAR, max_length=32)
        schema.add_field("scope_id", DataType.VARCHAR, max_length=128)
        schema.add_field("memory_id", DataType.VARCHAR, max_length=64)
        schema.add_field("chunk_index", DataType.INT64)
        indexes = self._client.prepare_index_params()
        indexes.add_index("vector", index_type="AUTOINDEX", metric_type=self._metric)
        self._client.create_collection(
            self._collection,
            schema=schema,
            index_params=indexes,
        )


def _vector_payload(value: MemoryVector) -> dict[str, object]:
    return {
        "id": value.id,
        "vector": list(value.vector),
        "tenant_id": value.tenant_id,
        "agent_id": value.agent_id or "",
        "scope_type": value.scope_type,
        "scope_id": value.scope_id,
        "memory_id": value.memory_id,
        "chunk_index": value.chunk_index,
    }


def memory_scope_filter(context: MemoryVectorSearchContext) -> str:
    rules = [
        '(scope_type == "tenant")',
        f'(scope_type == "agent" and scope_id == {_literal(context.agent_id)})',
        f'(scope_type == "user" and scope_id == {_literal(context.actor_id)})',
    ]
    if context.conversation_id:
        rules.append(
            f'(scope_type == "conversation" and scope_id == {_literal(context.conversation_id)})'
        )
    return (
        f"tenant_id == {_literal(context.tenant_id)} and "
        f'(agent_id == "" or agent_id == {_literal(context.agent_id)}) and '
        f"({' or '.join(rules)})"
    )


def _literal(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _memory_ids(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or not isinstance(value[0], list):
        return ()
    ids: list[str] = []
    for raw in cast(list[object], value[0]):
        if not isinstance(raw, dict):
            continue
        item = cast(dict[str, object], raw)
        memory_id = item.get("memory_id")
        if isinstance(memory_id, str) and memory_id and memory_id not in ids:
            ids.append(memory_id)
    return tuple(ids)
