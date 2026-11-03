from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from app.core.config import (
    MemoryCredentialsSection,
    MemoryEmbeddingSection,
    MemoryRuntimeSection,
    load_app_config,
)
from app.modules.memory.embedding import OpenAiCompatibleEmbeddingClient
from app.modules.memory.vector_store import MemoryVectorSearchContext, memory_scope_filter

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.asyncio
async def test_embedding_client_uses_explicit_memory_credential_reference() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"data": [{"embedding": [0.1, 0.2]}]})

    settings = load_app_config(ROOT / "config" / "dev.toml").model_copy(
        update={
            "memory": MemoryRuntimeSection(
                embedding=MemoryEmbeddingSection(
                    base_url="https://embedding.example.test/v1",
                    model="test-embedding",
                    credential_ref="embedding-key",
                    allowed_hosts=("embedding.example.test",),
                    extra_body={"dimensions": 1024, "encoding_format": "float"},
                )
            ),
            "memory_credentials": MemoryCredentialsSection(values={"embedding-key": "secret"}),
        }
    )

    result = await OpenAiCompatibleEmbeddingClient(
        settings, transport=httpx.MockTransport(handler)
    ).embed(("hello",))

    assert result == ((0.1, 0.2),)
    assert str(seen[0].url) == "https://embedding.example.test/v1/embeddings"
    assert seen[0].headers["authorization"] == "Bearer secret"
    assert json.loads(seen[0].content) == {
        "model": "test-embedding",
        "input": ["hello"],
        "dimensions": 1024,
        "encoding_format": "float",
    }


def test_vector_filter_enforces_tenant_agent_and_visible_scope() -> None:
    expression = memory_scope_filter(
        MemoryVectorSearchContext(
            tenant_id="tenant_a",
            agent_id="agent_a",
            actor_id="visitor_a",
            conversation_id="conversation_a",
        )
    )

    assert 'tenant_id == "tenant_a"' in expression
    assert 'agent_id == "agent_a"' in expression
    assert 'scope_id == "visitor_a"' in expression
    assert 'scope_id == "conversation_a"' in expression
    assert 'scope_type == "thread"' not in expression
