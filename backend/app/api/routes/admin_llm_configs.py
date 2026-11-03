from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session, require_permission
from app.core.request_id import get_request_id
from app.core.response import ApiResponse, ok
from app.modules.iam.permissions import LLM_CONFIGS_MANAGE, LLM_CONFIGS_READ
from app.modules.iam.service import AuthenticatedSession
from app.modules.llm_configs.schemas import (
    LlmConfigConnectionTestRequest,
    LlmConfigCreateRequest,
    LlmConfigUpdateRequest,
    LlmConfigView,
)
from app.modules.llm_configs.service import LlmConfigService
from app.modules.model_configs.schemas import ModelConnectionTestView

router = APIRouter()


def _service(request: Request, session: AsyncSession) -> LlmConfigService:
    return LlmConfigService(
        session,
        request.app.state.database,
        request.app.state.credential_cipher,
        request.app.state.settings,
    )


@router.get("/tenants/{tenant_id}/llm-configs", response_model=ApiResponse[list[LlmConfigView]])
async def list_llm_configs(
    tenant_id: str,
    request: Request,
    query: str | None = Query(default=None, max_length=300),
    authenticated: AuthenticatedSession = Depends(require_permission(LLM_CONFIGS_READ)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[list[LlmConfigView]]:
    data = await _service(request, session).list(authenticated.principal, tenant_id, query=query)
    return ok(data, get_request_id(request))


@router.post(
    "/tenants/{tenant_id}/llm-configs", response_model=ApiResponse[LlmConfigView], status_code=201
)
async def create_llm_config(
    tenant_id: str,
    payload: LlmConfigCreateRequest,
    request: Request,
    authenticated: AuthenticatedSession = Depends(
        require_permission(LLM_CONFIGS_MANAGE, csrf=True)
    ),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[LlmConfigView]:
    data = await _service(request, session).create(authenticated.principal, tenant_id, payload)
    return ok(data, get_request_id(request))


@router.patch(
    "/tenants/{tenant_id}/llm-configs/{config_id}", response_model=ApiResponse[LlmConfigView]
)
async def update_llm_config(
    tenant_id: str,
    config_id: str,
    payload: LlmConfigUpdateRequest,
    request: Request,
    authenticated: AuthenticatedSession = Depends(
        require_permission(LLM_CONFIGS_MANAGE, csrf=True)
    ),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[LlmConfigView]:
    data = await _service(request, session).update(
        authenticated.principal, tenant_id, config_id, payload
    )
    return ok(data, get_request_id(request))


@router.post(
    "/tenants/{tenant_id}/llm-configs/{config_id}/connection-test",
    response_model=ApiResponse[ModelConnectionTestView],
)
async def test_llm_config_connection(
    tenant_id: str,
    config_id: str,
    request: Request,
    authenticated: AuthenticatedSession = Depends(
        require_permission(LLM_CONFIGS_MANAGE, csrf=True)
    ),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[ModelConnectionTestView]:
    data = await _service(request, session).test_connection(
        authenticated.principal, tenant_id, config_id
    )
    return ok(data, get_request_id(request))


@router.post(
    "/tenants/{tenant_id}/llm-configs/connection-test",
    response_model=ApiResponse[ModelConnectionTestView],
)
async def test_llm_config_draft_connection(
    tenant_id: str,
    payload: LlmConfigConnectionTestRequest,
    request: Request,
    authenticated: AuthenticatedSession = Depends(
        require_permission(LLM_CONFIGS_MANAGE, csrf=True)
    ),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[ModelConnectionTestView]:
    data = await _service(request, session).test_draft_connection(
        authenticated.principal, tenant_id, payload
    )
    return ok(data, get_request_id(request))
