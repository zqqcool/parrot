from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session, require_permission
from app.core.request_id import get_request_id
from app.core.response import ApiResponse, ok
from app.modules.embedding_configs.schemas import (
    EmbeddingConfigConnectionTestRequest,
    EmbeddingConfigCreateRequest,
    EmbeddingConfigUpdateRequest,
    EmbeddingConfigView,
)
from app.modules.embedding_configs.service import EmbeddingConfigService
from app.modules.iam.permissions import LLM_CONFIGS_MANAGE, LLM_CONFIGS_READ
from app.modules.iam.service import AuthenticatedSession
from app.modules.model_configs.schemas import ModelConnectionTestView
from app.modules.model_providers.schemas import ModelProviderView
from app.modules.model_providers.service import ModelProviderCatalogService
from app.modules.reranker_configs.schemas import (
    RerankerConfigConnectionTestRequest,
    RerankerConfigCreateRequest,
    RerankerConfigUpdateRequest,
    RerankerConfigView,
)
from app.modules.reranker_configs.service import RerankerConfigService

router = APIRouter()


@router.get(
    "/tenants/{tenant_id}/model-providers",
    response_model=ApiResponse[list[ModelProviderView]],
)
async def list_model_providers(
    tenant_id: str,
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_permission(LLM_CONFIGS_READ)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[list[ModelProviderView]]:
    service = ModelProviderCatalogService(session, request.app.state.database)
    return ok(await service.list(authenticated.principal, tenant_id), get_request_id(request))


def _embedding(request: Request, session: AsyncSession) -> EmbeddingConfigService:
    return EmbeddingConfigService(
        session,
        request.app.state.database,
        request.app.state.credential_cipher,
        request.app.state.settings,
    )


def _reranker(request: Request, session: AsyncSession) -> RerankerConfigService:
    return RerankerConfigService(
        session,
        request.app.state.database,
        request.app.state.credential_cipher,
        request.app.state.settings,
    )


@router.get(
    "/tenants/{tenant_id}/embedding-configs", response_model=ApiResponse[list[EmbeddingConfigView]]
)
async def list_embedding_configs(
    tenant_id: str,
    request: Request,
    query: str | None = Query(default=None, max_length=300),
    authenticated: AuthenticatedSession = Depends(require_permission(LLM_CONFIGS_READ)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[list[EmbeddingConfigView]]:
    return ok(
        await _embedding(request, session).list(authenticated.principal, tenant_id, query=query),
        get_request_id(request),
    )


@router.post(
    "/tenants/{tenant_id}/embedding-configs",
    response_model=ApiResponse[EmbeddingConfigView],
    status_code=201,
)
async def create_embedding_config(
    tenant_id: str,
    payload: EmbeddingConfigCreateRequest,
    request: Request,
    authenticated: AuthenticatedSession = Depends(
        require_permission(LLM_CONFIGS_MANAGE, csrf=True)
    ),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[EmbeddingConfigView]:
    return ok(
        await _embedding(request, session).create(authenticated.principal, tenant_id, payload),
        get_request_id(request),
    )


@router.patch(
    "/tenants/{tenant_id}/embedding-configs/{config_id}",
    response_model=ApiResponse[EmbeddingConfigView],
)
async def update_embedding_config(
    tenant_id: str,
    config_id: str,
    payload: EmbeddingConfigUpdateRequest,
    request: Request,
    authenticated: AuthenticatedSession = Depends(
        require_permission(LLM_CONFIGS_MANAGE, csrf=True)
    ),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[EmbeddingConfigView]:
    return ok(
        await _embedding(request, session).update(
            authenticated.principal, tenant_id, config_id, payload
        ),
        get_request_id(request),
    )


@router.post(
    "/tenants/{tenant_id}/embedding-configs/{config_id}/connection-test",
    response_model=ApiResponse[ModelConnectionTestView],
)
async def test_embedding_config_connection(
    tenant_id: str,
    config_id: str,
    request: Request,
    authenticated: AuthenticatedSession = Depends(
        require_permission(LLM_CONFIGS_MANAGE, csrf=True)
    ),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[ModelConnectionTestView]:
    return ok(
        await _embedding(request, session).test_connection(
            authenticated.principal, tenant_id, config_id
        ),
        get_request_id(request),
    )


@router.post(
    "/tenants/{tenant_id}/embedding-configs/connection-test",
    response_model=ApiResponse[ModelConnectionTestView],
)
async def test_embedding_config_draft_connection(
    tenant_id: str,
    payload: EmbeddingConfigConnectionTestRequest,
    request: Request,
    authenticated: AuthenticatedSession = Depends(
        require_permission(LLM_CONFIGS_MANAGE, csrf=True)
    ),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[ModelConnectionTestView]:
    return ok(
        await _embedding(request, session).test_draft_connection(
            authenticated.principal, tenant_id, payload
        ),
        get_request_id(request),
    )


@router.delete(
    "/tenants/{tenant_id}/embedding-configs/{config_id}",
    response_model=ApiResponse[dict[str, bool]],
)
async def delete_embedding_config(
    tenant_id: str,
    config_id: str,
    request: Request,
    authenticated: AuthenticatedSession = Depends(
        require_permission(LLM_CONFIGS_MANAGE, csrf=True)
    ),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[dict[str, bool]]:
    await _embedding(request, session).delete(authenticated.principal, tenant_id, config_id)
    return ok({"deleted": True}, get_request_id(request))


@router.get(
    "/tenants/{tenant_id}/reranker-configs", response_model=ApiResponse[list[RerankerConfigView]]
)
async def list_reranker_configs(
    tenant_id: str,
    request: Request,
    query: str | None = Query(default=None, max_length=300),
    authenticated: AuthenticatedSession = Depends(require_permission(LLM_CONFIGS_READ)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[list[RerankerConfigView]]:
    return ok(
        await _reranker(request, session).list(authenticated.principal, tenant_id, query=query),
        get_request_id(request),
    )


@router.post(
    "/tenants/{tenant_id}/reranker-configs",
    response_model=ApiResponse[RerankerConfigView],
    status_code=201,
)
async def create_reranker_config(
    tenant_id: str,
    payload: RerankerConfigCreateRequest,
    request: Request,
    authenticated: AuthenticatedSession = Depends(
        require_permission(LLM_CONFIGS_MANAGE, csrf=True)
    ),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[RerankerConfigView]:
    return ok(
        await _reranker(request, session).create(authenticated.principal, tenant_id, payload),
        get_request_id(request),
    )


@router.patch(
    "/tenants/{tenant_id}/reranker-configs/{config_id}",
    response_model=ApiResponse[RerankerConfigView],
)
async def update_reranker_config(
    tenant_id: str,
    config_id: str,
    payload: RerankerConfigUpdateRequest,
    request: Request,
    authenticated: AuthenticatedSession = Depends(
        require_permission(LLM_CONFIGS_MANAGE, csrf=True)
    ),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[RerankerConfigView]:
    return ok(
        await _reranker(request, session).update(
            authenticated.principal, tenant_id, config_id, payload
        ),
        get_request_id(request),
    )


@router.post(
    "/tenants/{tenant_id}/reranker-configs/{config_id}/connection-test",
    response_model=ApiResponse[ModelConnectionTestView],
)
async def test_reranker_config_connection(
    tenant_id: str,
    config_id: str,
    request: Request,
    authenticated: AuthenticatedSession = Depends(
        require_permission(LLM_CONFIGS_MANAGE, csrf=True)
    ),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[ModelConnectionTestView]:
    return ok(
        await _reranker(request, session).test_connection(
            authenticated.principal, tenant_id, config_id
        ),
        get_request_id(request),
    )


@router.post(
    "/tenants/{tenant_id}/reranker-configs/connection-test",
    response_model=ApiResponse[ModelConnectionTestView],
)
async def test_reranker_config_draft_connection(
    tenant_id: str,
    payload: RerankerConfigConnectionTestRequest,
    request: Request,
    authenticated: AuthenticatedSession = Depends(
        require_permission(LLM_CONFIGS_MANAGE, csrf=True)
    ),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[ModelConnectionTestView]:
    return ok(
        await _reranker(request, session).test_draft_connection(
            authenticated.principal, tenant_id, payload
        ),
        get_request_id(request),
    )
