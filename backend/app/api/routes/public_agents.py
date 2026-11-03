from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.avatar_response import avatar_response
from app.api.dependencies import get_db_session
from app.core.request_id import get_request_id
from app.core.response import ApiResponse, ok
from app.modules.agents.schemas import AgentView
from app.modules.agents.service import AgentService
from app.modules.im.schemas import PublicImChannelView
from app.modules.im.service import ImChannelService

router = APIRouter()


@router.get("/agents", response_model=ApiResponse[list[AgentView]])
async def list_public_agents(
    request: Request,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1, le=100),
    search: str | None = Query(default=None, min_length=1, max_length=100),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[list[AgentView]]:
    data = await _agent_service(request, session).list_public(
        offset=offset,
        limit=limit,
        search=search,
    )
    return ok(data, get_request_id(request))


@router.get("/agents/{slug}", response_model=ApiResponse[AgentView])
async def get_public_agent(
    slug: str,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[AgentView]:
    model = await _agent_service(request, session).get_public(slug)
    return ok(AgentService.view(model), get_request_id(request))


@router.get("/agents/{slug}/channels", response_model=ApiResponse[list[PublicImChannelView]])
async def list_public_agent_channels(
    slug: str,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[list[PublicImChannelView]]:
    data = await _channel_service(request, session).list_public_agent_channels(slug)
    return ok(data, get_request_id(request))


@router.get("/agents/{slug}/avatar", response_class=Response)
async def get_public_agent_avatar(
    slug: str,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    avatar = await _agent_service(request, session).get_public_avatar(slug)
    return avatar_response(avatar.content, avatar.content_type)


def _agent_service(request: Request, session: AsyncSession) -> AgentService:
    return AgentService(
        session,
        request.app.state.database,
        object_storage=request.app.state.object_storage,
        max_avatar_bytes=request.app.state.settings.media.max_agent_avatar_bytes,
    )


def _channel_service(request: Request, session: AsyncSession) -> ImChannelService:
    return ImChannelService(session, request.app.state.database)
