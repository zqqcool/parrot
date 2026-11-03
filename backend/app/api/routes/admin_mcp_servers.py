from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session, require_permission
from app.core.request_id import get_request_id
from app.core.response import ApiResponse, ok
from app.modules.agent_runtime.mcp_executor import McpClientExecutor
from app.modules.agents.mcp_usage import AgentMcpUsage
from app.modules.iam.permissions import MCP_SERVERS_MANAGE, MCP_SERVERS_READ
from app.modules.iam.service import AuthenticatedSession
from app.modules.mcp_servers.schemas import (
    McpDiscoveredToolView,
    McpServerCreateRequest,
    McpServerUpdateRequest,
    McpServerView,
)
from app.modules.mcp_servers.service import McpServerService

router = APIRouter()


def _service(request: Request, session: AsyncSession) -> McpServerService:
    return McpServerService(
        session,
        request.app.state.database,
        request.app.state.credential_cipher,
        bound_agent_reader=AgentMcpUsage(session),
        dispatcher=request.app.state.task_dispatcher,
        mcp_executor=McpClientExecutor(
            request.app.state.settings, request.app.state.credential_cipher
        ),
    )


@router.get("/tenants/{tenant_id}/mcp-servers", response_model=ApiResponse[list[McpServerView]])
async def list_mcp_servers(
    tenant_id: str,
    request: Request,
    query: str | None = Query(default=None, max_length=300),
    authenticated: AuthenticatedSession = Depends(require_permission(MCP_SERVERS_READ)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[list[McpServerView]]:
    data = await _service(request, session).list(authenticated.principal, tenant_id, query=query)
    return ok(data, get_request_id(request))


@router.post(
    "/tenants/{tenant_id}/mcp-servers", response_model=ApiResponse[McpServerView], status_code=201
)
async def create_mcp_server(
    tenant_id: str,
    payload: McpServerCreateRequest,
    request: Request,
    authenticated: AuthenticatedSession = Depends(
        require_permission(MCP_SERVERS_MANAGE, csrf=True)
    ),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[McpServerView]:
    data = await _service(request, session).create(authenticated.principal, tenant_id, payload)
    return ok(data, get_request_id(request))


@router.patch(
    "/tenants/{tenant_id}/mcp-servers/{server_id}", response_model=ApiResponse[McpServerView]
)
async def update_mcp_server(
    tenant_id: str,
    server_id: str,
    payload: McpServerUpdateRequest,
    request: Request,
    authenticated: AuthenticatedSession = Depends(
        require_permission(MCP_SERVERS_MANAGE, csrf=True)
    ),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[McpServerView]:
    data = await _service(request, session).update(
        authenticated.principal, tenant_id, server_id, payload
    )
    return ok(data, get_request_id(request))


@router.post(
    "/tenants/{tenant_id}/mcp-servers/{server_id}/discover-tools",
    response_model=ApiResponse[list[McpDiscoveredToolView]],
)
async def discover_mcp_tools(
    tenant_id: str,
    server_id: str,
    request: Request,
    authenticated: AuthenticatedSession = Depends(
        require_permission(MCP_SERVERS_MANAGE, csrf=True)
    ),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[list[McpDiscoveredToolView]]:
    data = await _service(request, session).discover_tools(
        authenticated.principal, tenant_id, server_id
    )
    return ok(data, get_request_id(request))
