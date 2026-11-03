from __future__ import annotations

from starlette import status

from app.core.errors import AppError
from app.infrastructure.db.session import DatabaseManager
from app.modules.agent_runtime.taskboard_projection import project_task_board
from app.modules.agents.ports import AgentCatalogPort
from app.modules.iam.permissions import PLATFORM_TENANTS_MANAGE
from app.modules.iam.schemas import PrincipalContext, UserReference
from app.modules.iam.user_references import UserReferenceResolver
from app.modules.interactions.models import Interaction
from app.modules.runs.repository import RunRepository
from app.modules.runs.schemas import (
    ConversationMessageView,
    ConversationSummaryView,
    RunDiagnosticTraceView,
    RunEventView,
    RunRequesterReference,
    RunRequesterSummary,
    RunTaskBoardView,
    RunTaskView,
    RunView,
)


class RunService:
    def __init__(
        self,
        repository: RunRepository,
        database: DatabaseManager,
        agents: AgentCatalogPort,
    ) -> None:
        self.repository = repository
        self.database = database
        self.agents = agents

    async def list(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        *,
        run_status: str | None,
        agent_id: str | None,
        actor_type: str | None,
        actor_id: str | None,
        limit: int,
    ) -> list[RunView]:
        await self._enter(principal, tenant_id)
        self._validate_requester_filter(actor_type, actor_id)
        runs = await self.repository.list(
            tenant_id,
            status=run_status,
            agent_id=agent_id,
            actor_type=actor_type,
            actor_id=actor_id,
            limit=limit,
        )
        names = await self.agents.names(tenant_id, tuple({run.agent_id for run in runs}))
        requesters = await self._requesters(tenant_id, runs)
        return [
            self._view(run, names.get(run.agent_id) or run.agent_id, requesters[run.id])
            for run in runs
        ]

    async def get(self, principal: PrincipalContext, tenant_id: str, run_id: str) -> RunView:
        await self._enter(principal, tenant_id)
        run = await self.repository.get(tenant_id, run_id)
        if run is None:
            raise AppError("RESOURCE_NOT_FOUND", "Run not found", status.HTTP_404_NOT_FOUND)
        names = await self.agents.names(tenant_id, (run.agent_id,))
        requester = (await self._requesters(tenant_id, (run,)))[run.id]
        return self._view(run, names.get(run.agent_id) or run.agent_id, requester)

    async def requesters(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        *,
        actor_type: str | None = None,
        query: str | None = None,
        limit: int,
    ) -> list[RunRequesterSummary]:
        await self._enter(principal, tenant_id)
        resolver = UserReferenceResolver(self.repository.session)
        normalized = query.strip() if query else ""
        user_ids = await resolver.search_ids(tenant_id, normalized) if normalized else ()
        rows = await self.repository.list_requesters(
            tenant_id,
            actor_type=actor_type,
            query=normalized,
            user_ids=user_ids,
            limit=limit,
        )
        users = await resolver.resolve(
            tenant_id,
            (row.actor_id for row in rows if row.actor_type == "user"),
        )
        return [
            RunRequesterSummary(
                **self._requester_reference(row.actor_type, row.actor_id, users).model_dump(),
                run_count=row.run_count,
                active_run_count=row.active_run_count,
                latest_run_at=row.latest_run_at,
            )
            for row in rows
        ]

    async def events(
        self, principal: PrincipalContext, tenant_id: str, run_id: str
    ) -> list[RunEventView]:
        await self.get(principal, tenant_id, run_id)
        rows = await self.repository.list_events(tenant_id, run_id)
        return [
            RunEventView(
                type=row.type,
                event_id=row.id,
                request_id=row.request_id,
                occurred_at=row.created_at,
                sequence=row.sequence,
                data=row.data,
            )
            for row in rows
        ]

    async def diagnostic_traces(
        self, principal: PrincipalContext, tenant_id: str, run_id: str
    ) -> list[RunDiagnosticTraceView]:
        await self.get(principal, tenant_id, run_id)
        rows = await self.repository.list_diagnostic_traces(tenant_id, run_id)
        return [
            RunDiagnosticTraceView(
                id=row.id,
                type=row.type,
                sequence=row.sequence,
                occurred_at=row.created_at,
                data=row.data,
            )
            for row in rows
        ]

    async def conversations(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        *,
        actor_type: str,
        actor_id: str,
        limit: int,
    ) -> list[ConversationSummaryView]:
        await self._enter(principal, tenant_id)
        self._validate_requester_filter(actor_type, actor_id)
        rows = await self.repository.list_conversations(
            tenant_id, actor_type=actor_type, actor_id=actor_id, limit=limit
        )
        names = await self.agents.names(tenant_id, tuple({row.agent_id for row in rows}))
        return [
            ConversationSummaryView(
                conversation_id=row.conversation_id,
                agent_id=row.agent_id,
                agent_name=names.get(row.agent_id) or row.agent_id,
                message_count=row.message_count,
                active_run_count=row.active_run_count,
                latest_message_at=row.latest_message_at,
            )
            for row in rows
        ]

    async def conversation_messages(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        *,
        actor_type: str,
        actor_id: str,
        conversation_id: str,
    ) -> list[ConversationMessageView]:
        await self._enter(principal, tenant_id)
        self._validate_requester_filter(actor_type, actor_id)
        rows = await self.repository.list_conversation_messages(
            tenant_id,
            actor_type=actor_type,
            actor_id=actor_id,
            conversation_id=conversation_id,
        )
        return [
            ConversationMessageView(
                id=row.id,
                interaction_id=row.interaction_id,
                role=row.role,
                content=row.content,
                run_status=row.run_status,
                created_at=row.created_at,
            )
            for row in rows
        ]

    async def task_board(
        self, principal: PrincipalContext, tenant_id: str, run_id: str
    ) -> RunTaskBoardView:
        await self._enter(principal, tenant_id)
        run = await self.repository.get(tenant_id, run_id)
        if run is None:
            raise AppError("RESOURCE_NOT_FOUND", "Run not found", status.HTTP_404_NOT_FOUND)
        projection = project_task_board(run.input_payload)
        return RunTaskBoardView(
            id=projection.id,
            status=projection.status,
            tasks=[
                RunTaskView(
                    id=task.id,
                    title=task.title,
                    objective=task.objective,
                    kind=task.kind,
                    depends_on=list(task.depends_on),
                    status=task.status,
                    child_interaction_id=task.child_interaction_id,
                    result_summary=task.result_summary,
                )
                for task in projection.tasks
            ],
        )

    async def _enter(self, principal: PrincipalContext, tenant_id: str) -> None:
        if (
            principal.tenant_id != tenant_id
            and PLATFORM_TENANTS_MANAGE not in principal.permissions
        ):
            raise AppError("RESOURCE_NOT_FOUND", "Run not found", status.HTTP_404_NOT_FOUND)
        if "interactions.read.any" not in principal.permissions:
            raise AppError("FORBIDDEN", "Permission denied", status.HTTP_403_FORBIDDEN)
        await self.database.set_tenant(self.repository.session, tenant_id)

    async def _requesters(
        self, tenant_id: str, runs: tuple[Interaction, ...] | list[Interaction]
    ) -> dict[str, RunRequesterReference]:
        users = await UserReferenceResolver(self.repository.session).resolve(
            tenant_id,
            (run.actor_id for run in runs if run.actor_type == "user"),
        )
        return {
            run.id: self._requester_reference(run.actor_type, run.actor_id, users) for run in runs
        }

    @staticmethod
    def _requester_reference(
        actor_type: str, actor_id: str, users: dict[str, UserReference]
    ) -> RunRequesterReference:
        if actor_type == "user":
            user = users.get(actor_id)
            display_name = user.display_name if user is not None else "已移除用户"
        elif actor_type == "anonymous":
            display_name = f"匿名访客 · {actor_id[-8:]}"
        elif actor_type == "schedule":
            display_name = "定时任务"
        else:
            display_name = f"外部请求方 · {actor_id[-8:]}"
        return RunRequesterReference(
            actor_type=actor_type,
            actor_id=actor_id,
            display_name=display_name,
        )

    @staticmethod
    def _validate_requester_filter(actor_type: str | None, actor_id: str | None) -> None:
        if bool(actor_type) != bool(actor_id):
            raise AppError(
                "RUN_REQUESTER_FILTER_INVALID",
                "Requester type and ID must be provided together",
                status.HTTP_422_UNPROCESSABLE_CONTENT,
            )

    @staticmethod
    def _view(item: Interaction, agent_name: str, requester: RunRequesterReference) -> RunView:
        return RunView(
            id=item.id,
            tenant_id=item.tenant_id,
            agent_id=item.agent_id,
            agent_name=agent_name,
            actor_type=item.actor_type,
            requester=requester,
            entry_type=item.entry_type,
            input_type=item.input_type,
            input_summary=item.input_summary,
            status=item.status,
            runtime_execution_id=item.runtime_execution_id,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )
