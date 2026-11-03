from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session, require_permission
from app.core.request_id import get_request_id
from app.core.response import ApiResponse, ok
from app.modules.iam.permissions import KNOWLEDGE_SPACES_MANAGE, KNOWLEDGE_SPACES_READ
from app.modules.iam.service import AuthenticatedSession
from app.modules.knowledge.merge_schemas import (
    KnowledgeMergeSettingsUpdateRequest,
    KnowledgeMergeSettingsView,
)
from app.modules.knowledge.merge_settings import KnowledgeMergeSettingsService

router = APIRouter()


@router.get(
    "/tenants/{tenant_id}/knowledge/merge-settings",
    response_model=ApiResponse[KnowledgeMergeSettingsView],
)
async def get_merge_settings(
    tenant_id: str,
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_permission(KNOWLEDGE_SPACES_READ)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[KnowledgeMergeSettingsView]:
    return ok(
        await KnowledgeMergeSettingsService(session, request.app.state.database).get(
            authenticated.principal, tenant_id
        ),
        get_request_id(request),
    )


@router.put(
    "/tenants/{tenant_id}/knowledge/merge-settings",
    response_model=ApiResponse[KnowledgeMergeSettingsView],
)
async def update_merge_settings(
    tenant_id: str,
    payload: KnowledgeMergeSettingsUpdateRequest,
    request: Request,
    authenticated: AuthenticatedSession = Depends(
        require_permission(KNOWLEDGE_SPACES_MANAGE, csrf=True)
    ),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[KnowledgeMergeSettingsView]:
    return ok(
        await KnowledgeMergeSettingsService(session, request.app.state.database).update(
            authenticated.principal, tenant_id, payload
        ),
        get_request_id(request),
    )
