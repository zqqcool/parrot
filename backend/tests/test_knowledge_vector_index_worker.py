from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.dialects import postgresql

from app.core.config import load_app_config
from app.modules.knowledge.embedding import KnowledgeEmbeddingPort
from app.modules.knowledge.models import KnowledgeChunk, KnowledgeDocumentVersion
from app.modules.knowledge.vector_index_worker import KnowledgeVectorIndexWorker
from app.modules.knowledge.vector_jobs import (
    knowledge_space_index_status,
    knowledge_space_index_statuses_statement,
    knowledge_space_index_target_statement,
)
from app.modules.knowledge.vector_store import KnowledgeVectorStore

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        (("succeeded", "succeeded"), "ready"),
        (("succeeded", "queued"), "pending"),
        (("succeeded", "running"), "pending"),
        (("succeeded", "failed"), "failed"),
    ],
)
def test_knowledge_space_index_status_uses_terminal_precedence(
    statuses: tuple[str, ...], expected: str
) -> None:
    assert knowledge_space_index_status(statuses) == expected


def test_knowledge_space_index_status_query_is_scoped_to_one_space() -> None:
    statement = knowledge_space_index_statuses_statement(
        tenant_id="tenant_test",
        space_id="space_target",
        embedding_config_id="embedding_shared",
        index_revision=3,
    )
    compiled = statement.compile(dialect=postgresql.dialect())
    sql = str(compiled)

    assert "knowledge_documents.space_id" in sql
    assert "knowledge_vector_index_jobs.embedding_config_id" in sql
    assert "knowledge_vector_index_jobs.index_revision" in sql
    assert "space_target" in compiled.params.values()


def test_knowledge_space_index_target_is_locked_during_status_refresh() -> None:
    statement = knowledge_space_index_target_statement(
        tenant_id="tenant_test",
        document_version_id="version_test",
        embedding_config_id="embedding_shared",
        index_revision=3,
    )

    sql = str(statement.compile(dialect=postgresql.dialect()))

    assert "FOR UPDATE OF knowledge_spaces" in sql


def test_vector_worker_builds_milvus_safe_collection_names() -> None:
    worker = cast(
        KnowledgeVectorIndexWorker,
        SimpleNamespace(
            _settings=SimpleNamespace(
                knowledge=SimpleNamespace(vector=SimpleNamespace(collection="parrot_knowledge"))
            )
        ),
    )
    unsafe_profile_id = "embedding_ZIf-9vduGfxbAuG5mYwaSrFA"

    generated = KnowledgeVectorIndexWorker._collection(  # pyright: ignore[reportPrivateUsage]
        worker, profile_id=unsafe_profile_id
    )

    assert re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", generated)
    assert generated == KnowledgeVectorIndexWorker._collection(  # pyright: ignore[reportPrivateUsage]
        worker, profile_id=unsafe_profile_id
    )
    safe_profile_id = "embedding_0123456789abcdefghijklmn"
    assert (
        KnowledgeVectorIndexWorker._collection(  # pyright: ignore[reportPrivateUsage]
            worker, profile_id=safe_profile_id
        )
        == f"parrot_knowledge_{safe_profile_id[-24:]}"
    )


@pytest.mark.asyncio
async def test_vector_worker_preserves_chunk_and_version_identity() -> None:
    settings = load_app_config(ROOT / "config" / "dev.toml")
    embeddings = SimpleNamespace(embed=AsyncMock(return_value=((0.1, 0.2), (0.3, 0.4))))
    vectors = SimpleNamespace(delete=AsyncMock(), upsert=AsyncMock(), search=AsyncMock())
    worker = KnowledgeVectorIndexWorker(
        settings,
        cast(KnowledgeEmbeddingPort, embeddings),
        cast(KnowledgeVectorStore, vectors),
    )
    version = KnowledgeDocumentVersion(
        id="version_test",
        tenant_id="tenant_test",
        document_id="document_test",
        version=1,
        content_sha256="0" * 64,
        status="published",
        extraction_status="completed",
        chunk_size_chars=4000,
        chunk_overlap_chars=200,
        content="First\nSecond",
    )
    chunks = (
        _chunk("chunk_a", 1, "First"),
        _chunk("chunk_b", 2, "Second"),
    )

    result = await worker._build_vectors(version, chunks)  # pyright: ignore[reportPrivateUsage]

    assert tuple(item.chunk_id for item in result) == ("chunk_a", "chunk_b")
    assert all(item.document_version_id == version.id for item in result)
    assert all(item.tenant_id == "tenant_test" for item in result)
    assert all(item.space_id == "space_test" for item in result)
    embeddings.embed.assert_awaited_once_with(("First", "Second"))
    await worker._database.dispose()  # pyright: ignore[reportPrivateUsage]


def _chunk(chunk_id: str, ordinal: int, content: str) -> KnowledgeChunk:
    return KnowledgeChunk(
        id=chunk_id,
        tenant_id="tenant_test",
        space_id="space_test",
        document_version_id="version_test",
        ordinal=ordinal,
        content=content,
        citation_anchor=f"chunk-{ordinal}",
        search_vector=cast(object, ""),
    )
