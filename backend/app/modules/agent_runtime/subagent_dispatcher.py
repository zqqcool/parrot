from __future__ import annotations

import logging
from typing import Protocol, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent_runtime import AgentRuntimeProfile, profile_from_payload, profile_to_payload
from app.core.config import AppConfig
from app.core.ids import new_id
from app.core.task_dispatch import TaskDispatcher
from app.infrastructure.db.session import DatabaseManager
from app.modules.agent_runtime.active_skill import skill_context_payload
from app.modules.agent_runtime.contracts import ChatMessage
from app.modules.agent_runtime.resume_snapshot import (
    ResumeSnapshotTooLarge,
    create_resume_snapshot,
)
from app.modules.agent_runtime.subagent_result import normalize_child_result
from app.modules.agent_runtime.subagent_scheduling import select_spawnable_tasks
from app.modules.agent_runtime.subagent_scope import (
    derive_child_profile,
    derive_child_skill_context,
)
from app.modules.agent_runtime.subagent_task_prompt import render_task_contract
from app.modules.agent_runtime.taskboard import (
    TaskBoard,
    TaskBoardTask,
    create_task_board,
)
from app.modules.interactions.models import Interaction, InteractionEvent
from app.modules.interactions.runtime import RuntimeEventSink, RuntimeRequest

logger = logging.getLogger(__name__)


class SubagentDispatcherPort(Protocol):
    async def dispatch(
        self,
        request: RuntimeRequest,
        arguments: dict[str, object],
        events: RuntimeEventSink,
        *,
        resume_messages: list[ChatMessage] | None = None,
        source: str = "functional_planner",
        dispatch_call_id: str | None = None,
    ) -> dict[str, object]: ...

    async def settle_child(self, request: RuntimeRequest, events: RuntimeEventSink) -> None: ...


class SqlSubagentDispatcher:
    """Creates child interactions and advances one durable TaskBoard under parent row locks."""

    def __init__(
        self, settings: AppConfig, database: DatabaseManager, dispatcher: TaskDispatcher
    ) -> None:
        self._settings = settings
        self._database = database
        self._dispatcher = dispatcher

    async def dispatch(
        self,
        request: RuntimeRequest,
        arguments: dict[str, object],
        events: RuntimeEventSink,
        *,
        resume_messages: list[ChatMessage] | None = None,
        source: str = "functional_planner",
        dispatch_call_id: str | None = None,
    ) -> dict[str, object]:
        if request.profile is None or request.runtime_depth >= 1:
            return _rejected("SUBAGENT_DISPATCH_DISABLED", "Subagent dispatch is unavailable")
        try:
            board = create_task_board(
                arguments,
                request.text or "",
                request.runtime_depth,
                source=source,
                dispatch_call_id=dispatch_call_id,
                resume_plan=_resume_plan(request, source),
                max_tasks=self._settings.ai.agent_max_subagent_tasks,
                max_parallel=self._settings.ai.agent_max_parallel_subagents,
            )
            snapshot = (
                create_resume_snapshot(resume_messages) if resume_messages is not None else ()
            )
            board, dispatched = await self._persist_dispatch(request, board, snapshot)
        except ResumeSnapshotTooLarge as error:
            return _rejected("SUBAGENT_RESUME_CONTEXT_TOO_LARGE", str(error))
        except ValueError as error:
            return _rejected("SUBAGENT_TASKBOARD_INVALID", str(error))
        for child_id in dispatched:
            await self._dispatcher.dispatch_runtime(request.tenant_id, child_id)
        await events.append(
            tenant_id=request.tenant_id,
            interaction_id=request.interaction_id,
            request_id=request.request_id,
            event_type="ai.subagent.dispatched",
            data={"board_id": board.id, "child_interaction_ids": dispatched},
        )
        return {
            "status": "waiting_subagents",
            "board_id": board.id,
            "child_interaction_ids": dispatched,
        }

    async def settle_child(self, request: RuntimeRequest, events: RuntimeEventSink) -> None:
        if not request.parent_interaction_id or not request.subagent_task_id:
            return
        try:
            result = await self._settle(request)
        except Exception:
            logger.exception(
                "Subagent TaskBoard settlement failed",
                extra={"tenant_id": request.tenant_id, "interaction_id": request.interaction_id},
            )
            return
        if result is None:
            return
        for child_id in cast(tuple[str, ...], result["child_interaction_ids"]):
            await self._dispatcher.dispatch_runtime(request.tenant_id, child_id)
        if result["all_terminal"] is True:
            await self._dispatcher.dispatch_runtime(
                request.tenant_id, request.parent_interaction_id
            )
        await events.append(
            tenant_id=request.tenant_id,
            interaction_id=request.parent_interaction_id,
            request_id=request.request_id,
            event_type="ai.subagent.task.completed",
            data=result,
        )
        if result["all_terminal"] is True:
            await events.append(
                tenant_id=request.tenant_id,
                interaction_id=request.parent_interaction_id,
                request_id=request.request_id,
                event_type="ai.subagent.all_completed",
                data={"board_id": result["board_id"]},
            )

    async def _persist_dispatch(
        self,
        request: RuntimeRequest,
        board: TaskBoard,
        resume_messages: tuple[dict[str, object], ...],
    ) -> tuple[TaskBoard, tuple[str, ...]]:
        async with self._database.session() as session:
            await self._database.set_tenant(session, request.tenant_id)
            parent = await _locked_interaction(session, request.tenant_id, request.interaction_id)
            existing = _task_board(parent.input_payload)
            if existing is not None and existing.status == "waiting_subagents":
                # The original child dispatch is already durable. Returning no IDs
                # prevents a retry from enqueueing the same children again.
                return existing, ()
            if existing is not None:
                raise ValueError("this root interaction already has a TaskBoard")
            child_ids = await self._spawn_ready(session, parent, board)
            if not child_ids:
                raise ValueError("TaskBoard contains no dispatchable tasks")
            parent.input_payload = {
                **parent.input_payload,
                "task_board": board.to_dict(),
                "resume_messages": list(resume_messages),
            }
            parent.status = "waiting_subagents"
            await session.flush()
            return board, tuple(child_ids)

    async def _settle(self, request: RuntimeRequest) -> dict[str, object] | None:
        async with self._database.session() as session:
            await self._database.set_tenant(session, request.tenant_id)
            child = await _locked_interaction(session, request.tenant_id, request.interaction_id)
            parent = await _locked_interaction(
                session, request.tenant_id, request.parent_interaction_id or ""
            )
            board = _task_board(parent.input_payload)
            if board is None:
                return None
            task = next((item for item in board.tasks if item.id == request.subagent_task_id), None)
            if task is None or task.status in {"completed", "failed", "cancelled"}:
                return None
            if task.child_interaction_id != child.id:
                raise ValueError("Subagent interaction does not own this TaskBoard task")
            event_data = await _child_result(session, child)
            task_status, task_result = normalize_child_result(
                child.status, event_data, task.result_schema
            )
            board.settle(task.id, task_status, task_result)
            child_ids = await self._spawn_ready(session, parent, board)
            parent.input_payload = {**parent.input_payload, "task_board": board.to_dict()}
            parent.status = "accepted" if board.all_terminal() else "waiting_subagents"
            parent.runtime_recovery_lease_owner = None
            parent.runtime_recovery_lease_until = None
            await session.flush()
            return {
                "board_id": board.id,
                "task_id": task.id,
                "task_status": task.status,
                "child_interaction_ids": tuple(child_ids),
                "all_terminal": board.all_terminal(),
            }

    async def _spawn_ready(
        self,
        session: AsyncSession,
        parent: Interaction,
        board: TaskBoard,
    ) -> list[str]:
        child_ids: list[str] = []
        profile = _parent_profile(parent)
        if profile is None:
            raise ValueError("Parent Agent runtime profile is unavailable")
        active = tuple(task for task in board.tasks if task.status == "running")
        for task in select_spawnable_tasks(profile, board.ready_tasks(), active):
            child = await self._create_child(session, parent, board, task)
            board.mark_child(task.id, child.id)
            child_ids.append(child.id)
        return child_ids

    async def _create_child(
        self,
        session: AsyncSession,
        parent: Interaction,
        board: TaskBoard,
        task: TaskBoardTask,
    ) -> Interaction:
        parent_profile = _parent_profile(parent)
        runtime_agent_id = _payload_string(parent.input_payload, "runtime_agent_id")
        if parent_profile is None or runtime_agent_id is None:
            raise ValueError("Parent Agent runtime profile is unavailable")
        profile = derive_child_profile(parent_profile, task, source=board.source)
        skill_context = derive_child_skill_context(profile, task, source=board.source)
        child = Interaction(
            id=new_id("interaction"),
            tenant_id=parent.tenant_id,
            agent_id=parent.agent_id,
            actor_type=parent.actor_type,
            actor_id=parent.actor_id,
            entry_type="subagent",
            input_type="text",
            conversation_id=parent.conversation_id,
            parent_interaction_id=parent.id,
            root_interaction_id=parent.root_interaction_id or parent.id,
            subagent_task_id=task.id,
            runtime_depth=parent.runtime_depth + 1,
            status="accepted",
            input_summary=task.objective[:500],
            runtime_execution_id=f"runtime:{new_id('execution')}",
            input_payload={
                "text": render_task_contract(task, board.dependency_results(task)),
                "runtime_agent_id": runtime_agent_id,
                "request_id": new_id("request_subagent"),
                "profile": profile_to_payload(profile),
                "skill_context": skill_context_payload(skill_context),
                "subagent_task": task.to_dict(),
            },
        )
        session.add(child)
        session.add(
            InteractionEvent(
                id=new_id("event"),
                tenant_id=child.tenant_id,
                interaction_id=child.id,
                type="ai.interaction.accepted",
                request_id=cast(str, child.input_payload["request_id"]),
                sequence=1,
                data={"interaction_id": child.id, "status": "accepted", "parent": parent.id},
            )
        )
        await session.flush()
        return child


async def _locked_interaction(
    session: AsyncSession, tenant_id: str, interaction_id: str
) -> Interaction:
    item = await session.scalar(
        select(Interaction)
        .where(Interaction.tenant_id == tenant_id, Interaction.id == interaction_id)
        .with_for_update()
    )
    if item is None:
        raise ValueError("Interaction is unavailable")
    return item


def _task_board(payload: dict[str, object]) -> TaskBoard | None:
    raw = payload.get("task_board")
    if not isinstance(raw, dict):
        return None
    return TaskBoard.from_dict(cast(dict[str, object], raw))


def _parent_profile(parent: Interaction) -> AgentRuntimeProfile | None:
    return profile_from_payload(parent.input_payload.get("profile"))


async def _child_result(session: AsyncSession, child: Interaction) -> dict[str, object]:
    event = await session.scalar(
        select(InteractionEvent)
        .where(
            InteractionEvent.tenant_id == child.tenant_id,
            InteractionEvent.interaction_id == child.id,
            InteractionEvent.type.in_(
                ("ai.output.completed", "ai.output.failed", "ai.output.cancelled")
            ),
        )
        .order_by(InteractionEvent.sequence.desc())
    )
    data = event.data if event is not None else {}
    return {"status": child.status, "content": data.get("content"), "code": data.get("code")}


def _payload_string(payload: dict[str, object], key: str) -> str | None:
    value = payload.get(key)
    return value if isinstance(value, str) and value else None


def _rejected(code: str, message: str) -> dict[str, object]:
    return {"status": "rejected", "code": code, "message": message}


def _resume_plan(request: RuntimeRequest, source: str) -> dict[str, object]:
    if source != "agent_loop":
        return {}
    profile = request.profile
    context = request.skill_context
    context_restored = bool(
        context is not None and (context.primary is not None or context.supporting)
    )
    action = (
        "agent_loop" if profile is not None and profile.is_knowledge_only else "capability_lookup"
    )
    if context_restored:
        action = "capability_lookup"
    return {"action": action, "capability_prefetched": context_restored}
