from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import MemoryRuntimeSection
from app.infrastructure.db.session import DatabaseManager
from app.modules.memory.models import MemoryRecord
from app.modules.memory.retrieval import (
    MemorySearchContext,
    SemanticMemoryCandidates,
    SemanticMemorySearchPort,
    reciprocal_rank_fusion,
)
from app.modules.memory.runtime import MemoryRuntimeContext, SqlMemoryRuntime


class SessionContext:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def __aenter__(self) -> AsyncSession:
        return self.session

    async def __aexit__(self, *_: object) -> None:
        return None


class SemanticSearch(SemanticMemorySearchPort):
    async def search(
        self, context: MemorySearchContext, query: str, limit: int
    ) -> SemanticMemoryCandidates:
        del context, query, limit
        return SemanticMemoryCandidates(("memory_anchor",), True)


def test_reciprocal_rank_fusion_prioritizes_candidates_supported_by_both_retrievers() -> None:
    result = reciprocal_rank_fusion(("lexical_first", "shared"), ("shared", "semantic_only"), 60)

    assert result[0] == "shared"


@pytest.mark.asyncio
async def test_empty_memory_search_browses_memory_without_messages() -> None:
    record = MemoryRecord(
        id="memory_test",
        tenant_id="tenant_test",
        agent_id="agent_test",
        scope_type="agent",
        scope_id="agent_test",
        key="release_policy",
        content="Use staged rollout",
        memory_type="project_convention",
        retention_policy="user_managed",
        status="active",
        version=1,
        created_by_user_id="user_test",
        requires_confirmation=False,
    )
    session = cast(AsyncSession, SimpleNamespace(scalars=AsyncMock(return_value=[record])))
    database = SimpleNamespace(
        session=Mock(return_value=SessionContext(session)),
        set_tenant=AsyncMock(),
    )
    runtime = SqlMemoryRuntime(
        cast(DatabaseManager, database),
        MemoryRuntimeSection(search_limit=20),
    )
    context = MemoryRuntimeContext(
        tenant_id="tenant_test",
        agent_id="agent_test",
        actor_type="user",
        actor_id="user_test",
        interaction_id="interaction_test",
    )

    result = await runtime.handle(context, {"action": "search"})

    assert result["status"] == "ok"
    assert result["count"] == 1
    assert result["retrieval_method"] == "browse"
    assert result["items"] == [
        {
            "item_type": "memory",
            "id": "memory_test",
            "key": "release_policy",
            "scope_type": "agent",
            "memory_type": "project_convention",
            "status": "active",
            "version": 1,
            "requires_confirmation": False,
            "semantic_match": False,
        }
    ]


@pytest.mark.asyncio
async def test_keyword_memory_search_returns_hybrid_anchor_window_with_content() -> None:
    now = datetime.now(UTC)
    before = MemoryRecord(
        id="memory_before",
        tenant_id="tenant_test",
        agent_id="agent_test",
        scope_type="agent",
        scope_id="agent_test",
        key="before",
        content="Earlier release context",
        memory_type="project_convention",
        retention_policy="user_managed",
        status="active",
        version=1,
        created_by_user_id="user_test",
        created_at=now,
        updated_at=now,
    )
    anchor = MemoryRecord(
        id="memory_anchor",
        tenant_id="tenant_test",
        agent_id="agent_test",
        scope_type="agent",
        scope_id="agent_test",
        key="release_policy",
        content="Use staged rollout",
        memory_type="project_convention",
        retention_policy="user_managed",
        status="active",
        version=1,
        created_by_user_id="user_test",
        created_at=now,
        updated_at=now,
    )
    after = MemoryRecord(
        id="memory_after",
        tenant_id="tenant_test",
        agent_id="agent_test",
        scope_type="agent",
        scope_id="agent_test",
        key="after",
        content="Later release context",
        memory_type="project_convention",
        retention_policy="user_managed",
        status="active",
        version=1,
        created_by_user_id="user_test",
        created_at=now,
        updated_at=now,
    )
    session = cast(
        AsyncSession,
        SimpleNamespace(scalars=AsyncMock(side_effect=[[anchor], [anchor], [before], [after]])),
    )
    database = SimpleNamespace(
        session=Mock(return_value=SessionContext(session)),
        set_tenant=AsyncMock(),
    )
    runtime = SqlMemoryRuntime(
        cast(DatabaseManager, database),
        MemoryRuntimeSection(search_limit=20, context_max_tokens=128),
        semantic_search=SemanticSearch(),
    )
    context = MemoryRuntimeContext(
        tenant_id="tenant_test",
        agent_id="agent_test",
        actor_type="user",
        actor_id="user_test",
        interaction_id="interaction_test",
    )

    result = await runtime.handle(context, {"action": "search", "query": "release"})

    assert result["anchor_id"] == "memory_anchor"
    assert result["retrieval_method"] == "hybrid"
    items = cast(list[dict[str, object]], result["items"])
    assert [item["id"] for item in items] == [
        "memory_before",
        "memory_anchor",
        "memory_after",
    ]
    assert items[1]["content"] == "Use staged rollout"


@pytest.mark.asyncio
async def test_automatic_context_loads_only_bounded_pinned_memory() -> None:
    now = datetime.now(UTC)
    record = MemoryRecord(
        id="memory_preference",
        tenant_id="tenant_test",
        agent_id="agent_test",
        scope_type="user",
        scope_id="user_test",
        key="language",
        content="Use Chinese answers",
        memory_type="user_preference",
        retention_policy="user_managed",
        status="active",
        version=1,
        created_by_user_id="user_test",
        requires_confirmation=False,
        created_at=now,
        updated_at=now,
    )
    scalars = AsyncMock(return_value=[record])
    session = cast(AsyncSession, SimpleNamespace(scalars=scalars))
    database = SimpleNamespace(
        session=Mock(return_value=SessionContext(session)),
        set_tenant=AsyncMock(),
    )
    runtime = SqlMemoryRuntime(
        cast(DatabaseManager, database),
        MemoryRuntimeSection(context_limit=10, context_max_tokens=1_000),
    )
    context = MemoryRuntimeContext(
        tenant_id="tenant_test",
        agent_id="agent_test",
        actor_type="user",
        actor_id="user_test",
        interaction_id="interaction_test",
    )

    items = await runtime.pinned_for(context)

    assert [item.id for item in items] == ["memory_preference"]
    assert items[0].content == "Use Chinese answers"
    assert scalars.await_args is not None
    statement = str(scalars.await_args.args[0])
    assert "memory_records.status" in statement
    assert "memory_records.memory_type" in statement


@pytest.mark.asyncio
async def test_automatic_memory_recall_uses_resolved_query() -> None:
    now = datetime.now(UTC)
    anchor = MemoryRecord(
        id="memory_anchor",
        tenant_id="tenant_test",
        agent_id="agent_test",
        scope_type="agent",
        scope_id="agent_test",
        key="hotel_policy",
        content="Shanghai hotel booking convention",
        memory_type="long_term_fact",
        retention_policy="user_managed",
        status="active",
        version=1,
        created_by_user_id="user_test",
        requires_confirmation=False,
        created_at=now,
        updated_at=now,
    )
    session = cast(
        AsyncSession,
        SimpleNamespace(scalars=AsyncMock(side_effect=[[anchor], [anchor], [], []])),
    )
    database = SimpleNamespace(
        session=Mock(return_value=SessionContext(session)),
        set_tenant=AsyncMock(),
    )
    runtime = SqlMemoryRuntime(
        cast(DatabaseManager, database),
        MemoryRuntimeSection(search_limit=20, context_max_tokens=128),
        semantic_search=SemanticSearch(),
    )
    context = MemoryRuntimeContext(
        tenant_id="tenant_test",
        agent_id="agent_test",
        actor_type="user",
        actor_id="user_test",
        interaction_id="interaction_test",
    )

    recalled = await runtime.recall_for(context, "预定上海酒店")

    assert recalled.retrieval_method == "hybrid"
    assert [item.id for item in recalled.items] == ["memory_anchor"]
    assert recalled.items[0].content == "Shanghai hotel booking convention"
