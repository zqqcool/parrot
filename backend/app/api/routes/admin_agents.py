from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.avatar_response import avatar_response
from app.api.dependencies import get_db_session, require_permission
from app.core.request_id import get_request_id
from app.core.response import ApiResponse, ok
from app.modules.agent_runtime.mcp_executor import McpClientExecutor
from app.modules.agents.binding_service import AgentBindingService
from app.modules.agents.mcp_tool_recall_service import AgentMcpToolRecallService
from app.modules.agents.repository import AgentBindingRepository
from app.modules.agents.schemas import (
    AgentAdminView,
    AgentAvatarAttachRequest,
    AgentAvatarUploadGrantView,
    AgentAvatarUploadRequest,
    AgentCreateRequest,
    AgentLlmBindingsRequest,
    AgentLlmBindingsView,
    AgentMcpServerBindingsRequest,
    AgentMcpServerBindingsView,
    AgentMcpToolRecallRequest,
    AgentMcpToolRecallView,
    AgentSkillBindingsRequest,
    AgentSkillBindingsView,
    AgentSkillRecallRequest,
    AgentSkillRecallView,
    AgentTypeView,
    AgentUpdateRequest,
)
from app.modules.agents.service import AgentService
from app.modules.agents.skill_recall_service import AgentSkillRecallService
from app.modules.iam.permissions import AGENTS_MANAGE, AGENTS_READ
from app.modules.iam.service import AuthenticatedSession
from app.modules.llm_configs.service import LlmConfigService
from app.modules.mcp_servers.runtime_catalog import McpRuntimeCatalog
from app.modules.skills.service import SkillService

router = APIRouter()


def _binding_service(request: Request, session: AsyncSession) -> AgentBindingService:
    database = request.app.state.database
    return AgentBindingService(
        AgentBindingRepository(session),
        database,
        LlmConfigService(
            session,
            database,
            request.app.state.credential_cipher,
            request.app.state.settings,
        ),
        SkillService(session, database),
        McpRuntimeCatalog(session),
    )


def _agent_service(request: Request, session: AsyncSession) -> AgentService:
    database = request.app.state.database
    return AgentService(
        session,
        database,
        _binding_service(request, session),
        request.app.state.object_storage,
        request.app.state.settings.media.max_agent_avatar_bytes,
    )


def _skill_recall_service(request: Request, session: AsyncSession) -> AgentSkillRecallService:
    return AgentSkillRecallService(
        session,
        request.app.state.database,
        request.app.state.capability_search,
    )


def _mcp_tool_recall_service(request: Request, session: AsyncSession) -> AgentMcpToolRecallService:
    return AgentMcpToolRecallService(
        session,
        request.app.state.database,
        request.app.state.capability_search,
        McpClientExecutor(request.app.state.settings, request.app.state.credential_cipher),
    )


@router.get("/agent-types", response_model=ApiResponse[list[AgentTypeView]])
async def list_agent_types(
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_permission(AGENTS_READ)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[list[AgentTypeView]]:
    data = await _agent_service(request, session).list_types(authenticated.principal)
    return ok(data, get_request_id(request))


@router.get("/tenants/{tenant_id}/agents", response_model=ApiResponse[list[AgentAdminView]])
async def list_agents(
    tenant_id: str,
    request: Request,
    query: str | None = Query(default=None, max_length=300),
    authenticated: AuthenticatedSession = Depends(require_permission(AGENTS_READ)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[list[AgentAdminView]]:
    data = await _agent_service(request, session).list_for_tenant(
        authenticated.principal,
        tenant_id,
        query=query,
    )
    return ok(data, get_request_id(request))


@router.post(
    "/tenants/{tenant_id}/agents", response_model=ApiResponse[AgentAdminView], status_code=201
)
async def create_agent(
    tenant_id: str,
    payload: AgentCreateRequest,
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_permission(AGENTS_MANAGE, csrf=True)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[AgentAdminView]:
    data = await _agent_service(request, session).create(
        authenticated.principal,
        tenant_id,
        payload,
    )
    return ok(data, get_request_id(request))


@router.patch(
    "/tenants/{tenant_id}/agents/{agent_id}",
    response_model=ApiResponse[AgentAdminView],
)
async def update_agent(
    tenant_id: str,
    agent_id: str,
    payload: AgentUpdateRequest,
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_permission(AGENTS_MANAGE, csrf=True)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[AgentAdminView]:
    data = await _agent_service(request, session).update(
        authenticated.principal,
        tenant_id,
        agent_id,
        payload,
    )
    return ok(data, get_request_id(request))


@router.post(
    "/tenants/{tenant_id}/agents/{agent_id}/avatar-upload-grant",
    response_model=ApiResponse[AgentAvatarUploadGrantView],
)
async def issue_agent_avatar_upload(
    tenant_id: str,
    agent_id: str,
    payload: AgentAvatarUploadRequest,
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_permission(AGENTS_MANAGE, csrf=True)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[AgentAvatarUploadGrantView]:
    data = await _agent_service(request, session).issue_avatar_upload(
        authenticated.principal,
        tenant_id,
        agent_id,
        payload.content_type,
        payload.size_bytes,
    )
    return ok(
        AgentAvatarUploadGrantView(
            object_key=data.object_key,
            upload_key=data.upload_key,
            upload_token=data.upload_token,
            expires_at=data.expires_at,
        ),
        get_request_id(request),
    )


@router.put(
    "/tenants/{tenant_id}/agents/{agent_id}/avatar",
    response_model=ApiResponse[AgentAdminView],
)
async def attach_agent_avatar(
    tenant_id: str,
    agent_id: str,
    payload: AgentAvatarAttachRequest,
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_permission(AGENTS_MANAGE, csrf=True)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[AgentAdminView]:
    data = await _agent_service(request, session).attach_avatar(
        authenticated.principal, tenant_id, agent_id, payload.object_key
    )
    return ok(data, get_request_id(request))


@router.get("/tenants/{tenant_id}/agents/{agent_id}/avatar", response_class=Response)
async def get_agent_avatar(
    tenant_id: str,
    agent_id: str,
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_permission(AGENTS_READ)),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    avatar = await _agent_service(request, session).get_avatar(
        authenticated.principal,
        tenant_id,
        agent_id,
    )
    return avatar_response(avatar.content, avatar.content_type)


@router.get(
    "/tenants/{tenant_id}/agents/{agent_id}/llm-configs",
    response_model=ApiResponse[AgentLlmBindingsView],
)
async def get_agent_llm_bindings(
    tenant_id: str,
    agent_id: str,
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_permission(AGENTS_READ)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[AgentLlmBindingsView]:
    data = await _binding_service(request, session).get_llm_bindings(
        authenticated.principal, tenant_id, agent_id
    )
    return ok(data, get_request_id(request))


@router.put(
    "/tenants/{tenant_id}/agents/{agent_id}/llm-configs",
    response_model=ApiResponse[AgentLlmBindingsView],
)
async def replace_agent_llm_bindings(
    tenant_id: str,
    agent_id: str,
    payload: AgentLlmBindingsRequest,
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_permission(AGENTS_MANAGE, csrf=True)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[AgentLlmBindingsView]:
    data = await _binding_service(request, session).replace_llm_bindings(
        authenticated.principal, tenant_id, agent_id, payload.ids, payload.default_id
    )
    return ok(data, get_request_id(request))


@router.get(
    "/tenants/{tenant_id}/agents/{agent_id}/skills",
    response_model=ApiResponse[AgentSkillBindingsView],
)
async def get_agent_skill_bindings(
    tenant_id: str,
    agent_id: str,
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_permission(AGENTS_READ)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[AgentSkillBindingsView]:
    data = await _binding_service(request, session).get_skill_bindings(
        authenticated.principal, tenant_id, agent_id
    )
    return ok(data, get_request_id(request))


@router.post(
    "/tenants/{tenant_id}/agents/{agent_id}/skills:search",
    response_model=ApiResponse[AgentSkillRecallView],
)
async def search_agent_skills(
    tenant_id: str,
    agent_id: str,
    payload: AgentSkillRecallRequest,
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_permission(AGENTS_READ, csrf=True)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[AgentSkillRecallView]:
    data = await _skill_recall_service(request, session).search(
        authenticated.principal, tenant_id, agent_id, payload
    )
    return ok(data, get_request_id(request))


@router.put(
    "/tenants/{tenant_id}/agents/{agent_id}/skills",
    response_model=ApiResponse[AgentSkillBindingsView],
)
async def replace_agent_skill_bindings(
    tenant_id: str,
    agent_id: str,
    payload: AgentSkillBindingsRequest,
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_permission(AGENTS_MANAGE, csrf=True)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[AgentSkillBindingsView]:
    data = await _binding_service(request, session).replace_skill_bindings(
        authenticated.principal, tenant_id, agent_id, payload.ids
    )
    return ok(data, get_request_id(request))


@router.get(
    "/tenants/{tenant_id}/agents/{agent_id}/mcp-servers",
    response_model=ApiResponse[AgentMcpServerBindingsView],
)
async def get_agent_mcp_server_bindings(
    tenant_id: str,
    agent_id: str,
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_permission(AGENTS_READ)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[AgentMcpServerBindingsView]:
    data = await _binding_service(request, session).get_mcp_server_bindings(
        authenticated.principal, tenant_id, agent_id
    )
    return ok(data, get_request_id(request))


@router.post(
    "/tenants/{tenant_id}/agents/{agent_id}/mcp-tools:search",
    response_model=ApiResponse[AgentMcpToolRecallView],
)
async def search_agent_mcp_tools(
    tenant_id: str,
    agent_id: str,
    payload: AgentMcpToolRecallRequest,
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_permission(AGENTS_READ, csrf=True)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[AgentMcpToolRecallView]:
    data = await _mcp_tool_recall_service(request, session).search(
        authenticated.principal, tenant_id, agent_id, payload
    )
    return ok(data, get_request_id(request))


@router.put(
    "/tenants/{tenant_id}/agents/{agent_id}/mcp-servers",
    response_model=ApiResponse[AgentMcpServerBindingsView],
)
async def replace_agent_mcp_server_bindings(
    tenant_id: str,
    agent_id: str,
    payload: AgentMcpServerBindingsRequest,
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_permission(AGENTS_MANAGE, csrf=True)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[AgentMcpServerBindingsView]:
    data = await _binding_service(request, session).replace_mcp_server_bindings(
        authenticated.principal, tenant_id, agent_id, payload.ids
    )
    return ok(data, get_request_id(request))
