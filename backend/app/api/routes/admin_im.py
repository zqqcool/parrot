from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session, require_permission
from app.core.request_id import get_request_id
from app.core.response import ApiResponse, ok
from app.modules.iam.permissions import IM_CHANNELS_MANAGE, IM_CHANNELS_READ
from app.modules.iam.service import AuthenticatedSession
from app.modules.im.schemas import (
    ImAgentBindingRequest,
    ImAgentBindingView,
    ImChannelCreateRequest,
    ImChannelTypeView,
    ImChannelUpdateRequest,
    ImChannelView,
)
from app.modules.im.service import ImChannelService

router = APIRouter()


def _service(request: Request, session: AsyncSession) -> ImChannelService:
    return ImChannelService(session, request.app.state.database)


@router.get("/tenants/{tenant_id}/im/channels", response_model=ApiResponse[list[ImChannelView]])
async def list_channels(
    tenant_id: str,
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_permission(IM_CHANNELS_READ)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[list[ImChannelView]]:
    data = await _service(request, session).list_channels(authenticated.principal, tenant_id)
    return ok(data, get_request_id(request))


@router.get(
    "/tenants/{tenant_id}/im/channel-types", response_model=ApiResponse[list[ImChannelTypeView]]
)
async def list_channel_types(
    tenant_id: str,
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_permission(IM_CHANNELS_READ)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[list[ImChannelTypeView]]:
    data = await _service(request, session).list_channel_types(authenticated.principal, tenant_id)
    return ok(data, get_request_id(request))


@router.post(
    "/tenants/{tenant_id}/im/channels",
    response_model=ApiResponse[ImChannelView],
    status_code=201,
)
async def create_channel(
    tenant_id: str,
    payload: ImChannelCreateRequest,
    request: Request,
    authenticated: AuthenticatedSession = Depends(
        require_permission(IM_CHANNELS_MANAGE, csrf=True)
    ),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[ImChannelView]:
    data = await _service(request, session).create_channel(
        authenticated.principal, tenant_id, payload
    )
    return ok(data, get_request_id(request))


@router.patch(
    "/tenants/{tenant_id}/im/channels/{channel_id}", response_model=ApiResponse[ImChannelView]
)
async def update_channel(
    tenant_id: str,
    channel_id: str,
    payload: ImChannelUpdateRequest,
    request: Request,
    authenticated: AuthenticatedSession = Depends(
        require_permission(IM_CHANNELS_MANAGE, csrf=True)
    ),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[ImChannelView]:
    data = await _service(request, session).update_channel(
        authenticated.principal, tenant_id, channel_id, payload
    )
    return ok(data, get_request_id(request))


@router.get(
    "/tenants/{tenant_id}/agents/{agent_id}/im-bindings",
    response_model=ApiResponse[list[ImAgentBindingView]],
)
async def list_agent_bindings(
    tenant_id: str,
    agent_id: str,
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_permission(IM_CHANNELS_READ)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[list[ImAgentBindingView]]:
    data = await _service(request, session).list_agent_bindings(
        authenticated.principal, tenant_id, agent_id
    )
    return ok(data, get_request_id(request))


@router.put(
    "/tenants/{tenant_id}/im/agent-bindings", response_model=ApiResponse[ImAgentBindingView]
)
async def bind_agent(
    tenant_id: str,
    payload: ImAgentBindingRequest,
    request: Request,
    authenticated: AuthenticatedSession = Depends(
        require_permission(IM_CHANNELS_MANAGE, csrf=True)
    ),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[ImAgentBindingView]:
    data = await _service(request, session).bind_agent(authenticated.principal, tenant_id, payload)
    return ok(data, get_request_id(request))
