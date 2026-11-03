from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session, require_permission
from app.core.request_id import get_request_id
from app.core.response import ApiResponse, ok
from app.modules.agents.catalog import AgentCatalog
from app.modules.iam.permissions import INTERACTIONS_READ_ANY
from app.modules.iam.service import AuthenticatedSession
from app.modules.runs.repository import RunRepository
from app.modules.runs.schemas import (
    ConversationMessageView,
    ConversationSummaryView,
    RunDiagnosticTraceView,
    RunEventView,
    RunRequesterSummary,
    RunTaskBoardView,
    RunView,
)
from app.modules.runs.service import RunService

router = APIRouter()


def _service(request: Request, session: AsyncSession) -> RunService:
    return RunService(RunRepository(session), request.app.state.database, AgentCatalog(session))


@router.get("/tenants/{tenant_id}/runs", response_model=ApiResponse[list[RunView]])
async def list_runs(
    tenant_id: str,
    request: Request,
    run_status: str | None = Query(default=None, alias="status"),
    agent_id: str | None = None,
    actor_type: str | None = Query(default=None, min_length=1, max_length=32),
    actor_id: str | None = Query(default=None, min_length=1, max_length=64),
    limit: int = Query(default=10, ge=1, le=100),
    authenticated: AuthenticatedSession = Depends(require_permission(INTERACTIONS_READ_ANY)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[list[RunView]]:
    data = await _service(request, session).list(
        authenticated.principal,
        tenant_id,
        run_status=run_status,
        agent_id=agent_id,
        actor_type=actor_type,
        actor_id=actor_id,
        limit=limit,
    )
    return ok(data, get_request_id(request))


@router.get(
    "/tenants/{tenant_id}/runs/requesters",
    response_model=ApiResponse[list[RunRequesterSummary]],
)
async def list_run_requesters(
    tenant_id: str,
    request: Request,
    actor_type: str | None = Query(default=None, min_length=1, max_length=32),
    query: str | None = Query(default=None, max_length=300),
    limit: int = Query(default=100, ge=1, le=100),
    authenticated: AuthenticatedSession = Depends(require_permission(INTERACTIONS_READ_ANY)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[list[RunRequesterSummary]]:
    data = await _service(request, session).requesters(
        authenticated.principal,
        tenant_id,
        actor_type=actor_type,
        query=query,
        limit=limit,
    )
    return ok(data, get_request_id(request))


@router.get(
    "/tenants/{tenant_id}/runs/conversations",
    response_model=ApiResponse[list[ConversationSummaryView]],
)
async def list_conversations(
    tenant_id: str,
    request: Request,
    actor_type: str = Query(min_length=1, max_length=32),
    actor_id: str = Query(min_length=1, max_length=64),
    limit: int = Query(default=100, ge=1, le=100),
    authenticated: AuthenticatedSession = Depends(require_permission(INTERACTIONS_READ_ANY)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[list[ConversationSummaryView]]:
    data = await _service(request, session).conversations(
        authenticated.principal,
        tenant_id,
        actor_type=actor_type,
        actor_id=actor_id,
        limit=limit,
    )
    return ok(data, get_request_id(request))


@router.get(
    "/tenants/{tenant_id}/runs/conversations/{conversation_id}/messages",
    response_model=ApiResponse[list[ConversationMessageView]],
)
async def list_conversation_messages(
    tenant_id: str,
    conversation_id: str,
    request: Request,
    actor_type: str = Query(min_length=1, max_length=32),
    actor_id: str = Query(min_length=1, max_length=64),
    authenticated: AuthenticatedSession = Depends(require_permission(INTERACTIONS_READ_ANY)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[list[ConversationMessageView]]:
    data = await _service(request, session).conversation_messages(
        authenticated.principal,
        tenant_id,
        actor_type=actor_type,
        actor_id=actor_id,
        conversation_id=conversation_id,
    )
    return ok(data, get_request_id(request))


@router.get("/tenants/{tenant_id}/runs/{run_id}", response_model=ApiResponse[RunView])
async def get_run(
    tenant_id: str,
    run_id: str,
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_permission(INTERACTIONS_READ_ANY)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[RunView]:
    data = await _service(request, session).get(authenticated.principal, tenant_id, run_id)
    return ok(data, get_request_id(request))


@router.get(
    "/tenants/{tenant_id}/runs/{run_id}/diagnostic-traces",
    response_model=ApiResponse[list[RunDiagnosticTraceView]],
)
async def list_run_diagnostic_traces(
    tenant_id: str,
    run_id: str,
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_permission(INTERACTIONS_READ_ANY)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[list[RunDiagnosticTraceView]]:
    data = await _service(request, session).diagnostic_traces(
        authenticated.principal, tenant_id, run_id
    )
    return ok(data, get_request_id(request))


@router.get(
    "/tenants/{tenant_id}/runs/{run_id}/task-board",
    response_model=ApiResponse[RunTaskBoardView],
)
async def get_run_task_board(
    tenant_id: str,
    run_id: str,
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_permission(INTERACTIONS_READ_ANY)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[RunTaskBoardView]:
    data = await _service(request, session).task_board(authenticated.principal, tenant_id, run_id)
    return ok(data, get_request_id(request))


@router.get(
    "/tenants/{tenant_id}/runs/{run_id}/events",
    response_model=ApiResponse[list[RunEventView]],
)
async def list_run_events(
    tenant_id: str,
    run_id: str,
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_permission(INTERACTIONS_READ_ANY)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[list[RunEventView]]:
    data = await _service(request, session).events(authenticated.principal, tenant_id, run_id)
    return ok(data, get_request_id(request))
