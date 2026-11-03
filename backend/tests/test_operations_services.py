from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.infrastructure.db.session import DatabaseManager
from app.modules.agents.ports import AgentCatalogPort, AgentRuntimeTarget
from app.modules.iam.models import User
from app.modules.iam.schemas import PrincipalContext
from app.modules.iam.user_references import UserReferenceResolver
from app.modules.interactions.models import Interaction, InteractionDiagnosticTrace
from app.modules.interactions.runtime import RuntimePort, RuntimeRequest, RuntimeResult
from app.modules.interactions.service import InteractionService, InteractionSubmission
from app.modules.memory.models import MemoryRecord
from app.modules.memory.schemas import MemoryUpdateRequest
from app.modules.memory.service import MemoryService
from app.modules.runs.repository import ConversationSummaryRow, RunRepository, RunRequesterRow
from app.modules.runs.service import RunService
from app.modules.schedules.models import ScheduledTask, ScheduleExecution
from app.modules.schedules.service import ScheduleService


def principal(*permissions: str) -> PrincipalContext:
    return PrincipalContext(
        tenant_id="tenant_test",
        subject_id="user_test",
        username="operator",
        display_name="Operator",
        permissions=permissions,
        tenants=(),
        must_change_password=False,
        request_id="req_test",
    )


@pytest.mark.asyncio
async def test_runs_are_projected_from_interactions_with_agent_names() -> None:
    now = datetime.now(UTC)
    interaction = Interaction(
        id="interaction_test",
        tenant_id="tenant_test",
        agent_id="agent_test",
        actor_type="schedule",
        actor_id="schedule_test",
        entry_type="schedule",
        input_type="text",
        input_summary="Summarize",
        status="completed",
        created_at=now,
        updated_at=now,
    )
    repository = SimpleNamespace(session=object(), list=AsyncMock(return_value=[interaction]))
    database = SimpleNamespace(set_tenant=AsyncMock())
    agents = SimpleNamespace(names=AsyncMock(return_value={"agent_test": "Assistant"}))
    service = RunService(
        cast(RunRepository, repository),
        cast(DatabaseManager, database),
        cast(AgentCatalogPort, agents),
    )

    result = await service.list(
        principal("interactions.read.any"),
        "tenant_test",
        run_status=None,
        agent_id=None,
        actor_type=None,
        actor_id=None,
        limit=20,
    )

    assert result[0].id == "interaction_test"
    assert result[0].agent_name == "Assistant"
    assert result[0].requester.display_name == "定时任务"
    agents.names.assert_awaited_once_with("tenant_test", ("agent_test",))


@pytest.mark.asyncio
async def test_run_requesters_keep_user_and_anonymous_identities_distinct() -> None:
    now = datetime.now(UTC)
    user = User(
        id="user_test",
        username="operator",
        normalized_username="operator",
        display_name="Operator",
    )
    session = SimpleNamespace(scalars=AsyncMock(return_value=[user]))
    repository = SimpleNamespace(
        session=session,
        list_requesters=AsyncMock(
            return_value=[
                RunRequesterRow("user", "user_test", 3, 1, now),
                RunRequesterRow("anonymous", "visitor_abcdefgh", 2, 0, now),
            ]
        ),
    )
    service = RunService(
        cast(RunRepository, repository),
        cast(DatabaseManager, SimpleNamespace(set_tenant=AsyncMock())),
        cast(AgentCatalogPort, SimpleNamespace()),
    )

    result = await service.requesters(principal("interactions.read.any"), "tenant_test", limit=100)

    assert [item.display_name for item in result] == ["Operator", "匿名访客 · abcdefgh"]
    assert [item.active_run_count for item in result] == [1, 0]


@pytest.mark.asyncio
async def test_run_requester_search_resolves_users_before_database_limit() -> None:
    now = datetime.now(UTC)
    user = User(
        id="user_test",
        username="operator",
        normalized_username="operator",
        display_name="Operator",
    )
    session = SimpleNamespace(scalars=AsyncMock(side_effect=[["user_test"], [user]]))
    list_requesters = AsyncMock(return_value=[RunRequesterRow("user", "user_test", 3, 1, now)])
    service = RunService(
        cast(RunRepository, SimpleNamespace(session=session, list_requesters=list_requesters)),
        cast(DatabaseManager, SimpleNamespace(set_tenant=AsyncMock())),
        cast(AgentCatalogPort, SimpleNamespace()),
    )

    result = await service.requesters(
        principal("interactions.read.any"),
        "tenant_test",
        actor_type="user",
        query="Operator",
        limit=100,
    )

    assert result[0].display_name == "Operator"
    list_requesters.assert_awaited_once_with(
        "tenant_test",
        actor_type="user",
        query="Operator",
        user_ids=("user_test",),
        limit=100,
    )


@pytest.mark.asyncio
async def test_run_conversations_are_scoped_to_the_selected_requester() -> None:
    now = datetime.now(UTC)
    repository = SimpleNamespace(
        session=object(),
        list_conversations=AsyncMock(
            return_value=[
                ConversationSummaryRow(
                    conversation_id="conversation_one",
                    agent_id="agent_test",
                    message_count=4,
                    active_run_count=1,
                    latest_message_at=now,
                )
            ]
        ),
    )
    service = RunService(
        cast(RunRepository, repository),
        cast(DatabaseManager, SimpleNamespace(set_tenant=AsyncMock())),
        cast(
            AgentCatalogPort,
            SimpleNamespace(names=AsyncMock(return_value={"agent_test": "Agent"})),
        ),
    )

    result = await service.conversations(
        principal("interactions.read.any"),
        "tenant_test",
        actor_type="anonymous",
        actor_id="visitor_test",
        limit=100,
    )

    assert result[0].conversation_id == "conversation_one"
    assert result[0].agent_name == "Agent"
    repository.list_conversations.assert_awaited_once_with(
        "tenant_test", actor_type="anonymous", actor_id="visitor_test", limit=100
    )


@pytest.mark.asyncio
async def test_run_task_board_exposes_only_safe_task_projection() -> None:
    now = datetime.now(UTC)
    interaction = Interaction(
        id="interaction_test",
        tenant_id="tenant_test",
        agent_id="agent_test",
        actor_type="anonymous",
        actor_id="visitor_test",
        entry_type="websocket",
        input_type="text",
        input_summary="Research release notes",
        status="completed",
        input_payload={
            "runtime_agent_id": "private-runtime-id",
            "task_board": {
                "id": "taskboard_test",
                "status": "completed",
                "source": "planner",
                "tasks": [
                    {
                        "id": "task_one",
                        "title": "Research",
                        "objective": "Find release notes",
                        "kind": "information_lookup",
                        "depends_on": [],
                        "budget": {"timeout_seconds": 30, "max_tool_calls": 2},
                        "output_schema": {},
                        "tool_hints": ["web-search"],
                        "source_hints": ["official docs"],
                        "source_provenance": {},
                        "dedupe_key": "research",
                        "status": "completed",
                        "child_interaction_id": "interaction_child",
                        "result": {"status": "completed", "content": "Found the release notes."},
                    }
                ],
            },
        },
        created_at=now,
        updated_at=now,
    )
    repository = SimpleNamespace(session=object(), get=AsyncMock(return_value=interaction))
    service = RunService(
        cast(RunRepository, repository),
        cast(DatabaseManager, SimpleNamespace(set_tenant=AsyncMock())),
        cast(AgentCatalogPort, SimpleNamespace()),
    )

    result = await service.task_board(
        principal("interactions.read.any"), "tenant_test", interaction.id
    )

    assert result.id == "taskboard_test"
    assert result.tasks[0].result_summary == "Found the release notes."
    assert "runtime_agent_id" not in result.model_dump_json()
    assert "tool_hints" not in result.model_dump_json()


@pytest.mark.asyncio
async def test_run_diagnostic_traces_are_projected_only_for_visible_runs() -> None:
    now = datetime.now(UTC)
    interaction = Interaction(
        id="interaction_test",
        tenant_id="tenant_test",
        agent_id="agent_test",
        actor_type="anonymous",
        actor_id="visitor_test",
        entry_type="websocket",
        input_type="text",
        input_summary="Inspect trace",
        status="completed",
        created_at=now,
        updated_at=now,
    )
    trace = InteractionDiagnosticTrace(
        id="trace_test",
        tenant_id="tenant_test",
        interaction_id=interaction.id,
        type="model.request",
        sequence=1,
        data={"phase": "agent_loop", "messages": []},
        created_at=now,
        updated_at=now,
    )
    repository = SimpleNamespace(
        session=object(),
        get=AsyncMock(return_value=interaction),
        list_diagnostic_traces=AsyncMock(return_value=[trace]),
    )
    service = RunService(
        cast(RunRepository, repository),
        cast(DatabaseManager, SimpleNamespace(set_tenant=AsyncMock())),
        cast(
            AgentCatalogPort, SimpleNamespace(names=AsyncMock(return_value={"agent_test": "Agent"}))
        ),
    )

    result = await service.diagnostic_traces(
        principal("interactions.read.any"), "tenant_test", interaction.id
    )

    assert result[0].id == "trace_test"
    assert result[0].data == {"phase": "agent_loop", "messages": []}
    repository.list_diagnostic_traces.assert_awaited_once_with("tenant_test", interaction.id)


@pytest.mark.asyncio
async def test_memory_list_and_version_conflict_are_tenant_scoped() -> None:
    now = datetime.now(UTC)
    record = MemoryRecord(
        id="memory_test",
        tenant_id="tenant_test",
        agent_id="agent_test",
        scope_type="tenant",
        scope_id="tenant_test",
        key="policy",
        content="Use staged rollout",
        memory_type="project_convention",
        retention_policy="user_managed",
        status="active",
        version=2,
        created_by_user_id="user_test",
        created_at=now,
        updated_at=now,
    )
    conflict = SimpleNamespace(scalar_one_or_none=Mock(return_value=None))
    session = SimpleNamespace(
        scalars=AsyncMock(side_effect=([record], [])),
        scalar=AsyncMock(return_value=record),
        execute=AsyncMock(return_value=conflict),
    )
    database = SimpleNamespace(set_tenant=AsyncMock())
    service = MemoryService(
        cast(AsyncSession, session),
        cast(DatabaseManager, database),
        cast(
            AgentCatalogPort,
            SimpleNamespace(names=AsyncMock(return_value={"agent_test": "Support Agent"})),
        ),
    )

    records = await service.list(
        principal("memory.read"),
        "tenant_test",
        query="rollout",
        agent_id=None,
        record_status="active",
    )
    with pytest.raises(AppError) as error:
        await service.update(
            principal("memory.manage"),
            "tenant_test",
            "memory_test",
            MemoryUpdateRequest(content="new", expected_version=1),
        )

    assert records[0].version == 2
    assert records[0].agent_name == "Support Agent"
    assert records[0].created_by_actor_id == "user_test"
    assert error.value.code == "MEMORY_VERSION_CONFLICT"


@pytest.mark.asyncio
async def test_agent_memory_view_browses_agent_context_and_paginates() -> None:
    now = datetime.now(UTC)
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
        created_at=now,
        updated_at=now,
    )
    session = SimpleNamespace(
        scalar=AsyncMock(return_value=1),
        scalars=AsyncMock(side_effect=[[record], []]),
    )
    agents = SimpleNamespace(
        exists=AsyncMock(return_value=True),
        names=AsyncMock(return_value={"agent_test": "Support Agent"}),
    )
    database = SimpleNamespace(set_tenant=AsyncMock())
    service = MemoryService(
        cast(AsyncSession, session),
        cast(DatabaseManager, database),
        cast(AgentCatalogPort, agents),
    )

    result = await service.search_agent_visible(
        principal("memory.read"),
        "tenant_test",
        agent_id="agent_test",
        actor_id=None,
        query=None,
        offset=20,
        limit=20,
    )

    assert result.total == 1
    assert result.offset == 20
    assert result.limit == 20
    assert result.mode == "browse"
    assert result.items[0].id == "memory_test"
    assert result.items[0].agent_name == "Support Agent"
    assert result.items[0].created_by_actor_id == "user_test"
    agents.exists.assert_awaited_once_with("tenant_test", "agent_test")


@pytest.mark.asyncio
async def test_agent_memory_view_hides_unknown_agent_and_user() -> None:
    service = MemoryService(
        cast(AsyncSession, SimpleNamespace()),
        cast(DatabaseManager, SimpleNamespace(set_tenant=AsyncMock())),
        cast(AgentCatalogPort, SimpleNamespace(exists=AsyncMock(return_value=False))),
    )

    with pytest.raises(AppError) as error:
        await service.search_agent_visible(
            principal("memory.read"),
            "tenant_test",
            agent_id="agent_missing",
            actor_id="user_missing",
            query=None,
            offset=0,
            limit=20,
        )

    assert error.value.code == "RESOURCE_NOT_FOUND"


@pytest.mark.asyncio
async def test_agent_memory_view_hides_user_outside_tenant() -> None:
    session = SimpleNamespace(scalars=AsyncMock(return_value=[]))
    service = MemoryService(
        cast(AsyncSession, session),
        cast(DatabaseManager, SimpleNamespace(set_tenant=AsyncMock())),
        cast(AgentCatalogPort, SimpleNamespace(exists=AsyncMock(return_value=True))),
    )

    with pytest.raises(AppError) as error:
        await service.search_agent_visible(
            principal("memory.read"),
            "tenant_test",
            agent_id="agent_test",
            actor_id="user_other_tenant",
            query=None,
            offset=0,
            limit=20,
        )

    assert error.value.code == "RESOURCE_NOT_FOUND"


@pytest.mark.asyncio
async def test_user_reference_resolver_returns_only_safe_display_fields() -> None:
    user = User(
        id="user_test",
        username="operator",
        normalized_username="operator",
        email="operator@example.test",
        display_name="Operator",
        avatar_key="avatars/user_test.webp",
        avatar_content_type="image/webp",
    )
    session = cast(AsyncSession, SimpleNamespace(scalars=AsyncMock(return_value=[user])))

    resolved = await UserReferenceResolver(session).resolve("tenant_test", ("user_test", "missing"))

    assert resolved["user_test"].model_dump() == {
        "id": "user_test",
        "display_name": "Operator",
        "avatar_present": True,
    }


@pytest.mark.asyncio
async def test_runtime_submission_failure_is_persisted_and_mapped() -> None:
    no_existing = SimpleNamespace(scalar_one_or_none=Mock(return_value=None))
    session = SimpleNamespace(
        add=Mock(),
        execute=AsyncMock(return_value=no_existing),
        flush=AsyncMock(),
        commit=AsyncMock(),
    )
    database = SimpleNamespace(set_tenant=AsyncMock())
    runtime = SimpleNamespace(prepare=AsyncMock(side_effect=RuntimeError("unavailable")))
    service = InteractionService(
        cast(AsyncSession, session),
        cast(DatabaseManager, database),
        cast(RuntimePort, runtime),
    )

    with pytest.raises(AppError) as error:
        await service.submit(
            AgentRuntimeTarget("agent_test", "tenant_test", "runtime_test"),
            InteractionSubmission(
                actor_type="schedule",
                actor_id="schedule_test",
                entry_type="schedule",
                input_type="text",
                request_id="req_test",
                idempotency_key="execution_test",
                text="Summarize",
            ),
        )

    interaction = next(
        call.args[0] for call in session.add.call_args_list if isinstance(call.args[0], Interaction)
    )
    assert error.value.code == "AI_PROVIDER_UNAVAILABLE"
    assert interaction.status == "failed"


@pytest.mark.asyncio
async def test_remote_runtime_submission_sets_a_recovery_lease() -> None:
    no_existing = SimpleNamespace(scalar_one_or_none=Mock(return_value=None))
    session = SimpleNamespace(
        add=Mock(),
        execute=AsyncMock(return_value=no_existing),
        flush=AsyncMock(),
        commit=AsyncMock(),
    )
    database = SimpleNamespace(set_tenant=AsyncMock())

    async def dispatch(_: RuntimeRequest) -> None:
        interaction = next(
            call.args[0]
            for call in session.add.call_args_list
            if isinstance(call.args[0], Interaction)
        )
        assert interaction.status == "accepted"
        assert interaction.runtime_execution_id == "run_test"
        assert session.commit.await_count == 2

    runtime = SimpleNamespace(
        prepare=AsyncMock(
            return_value=RuntimeResult(
                status="accepted", execution_id="run_test", recovery_lease_seconds=90
            )
        ),
        dispatch=AsyncMock(side_effect=dispatch),
    )
    service = InteractionService(
        cast(AsyncSession, session),
        cast(DatabaseManager, database),
        cast(RuntimePort, runtime),
    )

    await service.submit(
        AgentRuntimeTarget("agent_test", "tenant_test", "runtime_test"),
        InteractionSubmission(
            actor_type="schedule",
            actor_id="schedule_test",
            entry_type="schedule",
            input_type="text",
            request_id="req_test",
            idempotency_key="execution_test",
            text="Summarize",
        ),
    )

    interaction = next(
        call.args[0] for call in session.add.call_args_list if isinstance(call.args[0], Interaction)
    )
    assert interaction.runtime_execution_id == "run_test"
    assert interaction.runtime_recovery_lease_owner == "runtime:run_test"
    assert interaction.runtime_recovery_lease_until is not None
    runtime.dispatch.assert_awaited_once()


@pytest.mark.asyncio
async def test_manual_schedule_execution_is_audited(monkeypatch: pytest.MonkeyPatch) -> None:
    task = ScheduledTask(
        id="schedule_test",
        tenant_id="tenant_test",
        agent_id="agent_test",
        creator_user_id="user_test",
        title="Daily",
        input_text="Summarize",
        schedule_type="recurring",
        cron_expr="0 9 * * 1-5",
        timezone="Asia/Shanghai",
        status="enabled",
    )
    execution = ScheduleExecution(
        id="execution_test",
        tenant_id="tenant_test",
        schedule_id="schedule_test",
        scheduled_for=datetime.now(UTC),
        trigger_type="manual",
        status="accepted",
    )
    session = SimpleNamespace(add=Mock())
    database = SimpleNamespace(set_tenant=AsyncMock())
    service = ScheduleService(
        cast(AsyncSession, session),
        cast(DatabaseManager, database),
        cast(RuntimePort, SimpleNamespace()),
        cast(AgentCatalogPort, SimpleNamespace()),
        "UTC",
    )
    monkeypatch.setattr(service, "_get", AsyncMock(return_value=task))
    monkeypatch.setattr(service, "_queue", AsyncMock(return_value=execution))
    monkeypatch.setattr(service, "_execute", AsyncMock())
    monkeypatch.setattr(service, "_execution_view", AsyncMock(return_value="execution-view"))

    result = await service.run_now(principal("schedules.manage"), "tenant_test", "schedule_test")

    assert result == "execution-view"
    audit = session.add.call_args.args[0]
    assert audit.action == "schedule.run_now"
    assert audit.metadata_json["execution_id"] == "execution_test"
