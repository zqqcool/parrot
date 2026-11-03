from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session, require_permission
from app.core.request_id import get_request_id
from app.core.response import ApiResponse, ok
from app.modules.agents.catalog import AgentCatalog
from app.modules.iam.permissions import (
    AGENTS_MANAGE,
    AGENTS_READ,
    KNOWLEDGE_ACCESS_MANAGE,
    KNOWLEDGE_DOCUMENTS_MANAGE,
    KNOWLEDGE_DOCUMENTS_READ,
    KNOWLEDGE_QUERY,
    KNOWLEDGE_SPACES_MANAGE,
    KNOWLEDGE_SPACES_READ,
)
from app.modules.iam.service import AuthenticatedSession
from app.modules.knowledge.citation_service import KnowledgeCitationService
from app.modules.knowledge.schemas import (
    AgentKnowledgeSearchTestRequest,
    AgentKnowledgeSearchTestView,
    AgentKnowledgeSpaceBindingsRequest,
    AgentKnowledgeSpaceBindingsView,
    KnowledgeCitationView,
    KnowledgeDocumentCreateRequest,
    KnowledgeDocumentView,
    KnowledgeSearchResult,
    KnowledgeSpaceAgentBindingsView,
    KnowledgeSpaceChunkingUpdateRequest,
    KnowledgeSpaceCreateRequest,
    KnowledgeSpaceGrantsRequest,
    KnowledgeSpaceGrantsView,
    KnowledgeSpaceRetrievalUpdateRequest,
    KnowledgeSpaceView,
)
from app.modules.knowledge.service import KnowledgeService
from app.modules.knowledge.space_deletion_service import KnowledgeSpaceDeletionService

router = APIRouter()


def _service(request: Request, session: AsyncSession) -> KnowledgeService:
    return KnowledgeService(
        session,
        request.app.state.database,
        AgentCatalog(session),
        settings=request.app.state.settings,
        cipher=request.app.state.credential_cipher,
        dispatcher=request.app.state.task_dispatcher,
    )


def _citation_service(request: Request, session: AsyncSession) -> KnowledgeCitationService:
    return KnowledgeCitationService(session, request.app.state.database)


@router.get(
    "/tenants/{tenant_id}/knowledge/spaces", response_model=ApiResponse[list[KnowledgeSpaceView]]
)
async def list_spaces(
    tenant_id: str,
    request: Request,
    query: str | None = Query(default=None, max_length=300),
    authenticated: AuthenticatedSession = Depends(require_permission(KNOWLEDGE_SPACES_READ)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[list[KnowledgeSpaceView]]:
    return ok(
        await _service(request, session).list_spaces(
            authenticated.principal, tenant_id, query=query
        ),
        get_request_id(request),
    )


@router.post(
    "/tenants/{tenant_id}/knowledge/spaces",
    response_model=ApiResponse[KnowledgeSpaceView],
    status_code=201,
)
async def create_space(
    tenant_id: str,
    payload: KnowledgeSpaceCreateRequest,
    request: Request,
    authenticated: AuthenticatedSession = Depends(
        require_permission(KNOWLEDGE_SPACES_MANAGE, csrf=True)
    ),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[KnowledgeSpaceView]:
    return ok(
        await _service(request, session).create_space(authenticated.principal, tenant_id, payload),
        get_request_id(request),
    )


@router.delete("/tenants/{tenant_id}/knowledge/spaces/{space_id}", response_model=ApiResponse[None])
async def delete_space(
    tenant_id: str,
    space_id: str,
    request: Request,
    authenticated: AuthenticatedSession = Depends(
        require_permission(KNOWLEDGE_SPACES_MANAGE, csrf=True)
    ),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[None]:
    await KnowledgeSpaceDeletionService(session, request.app.state.database).delete_space(
        authenticated.principal, tenant_id, space_id
    )
    return ok(None, get_request_id(request))


@router.patch(
    "/tenants/{tenant_id}/knowledge/spaces/{space_id}/chunking",
    response_model=ApiResponse[KnowledgeSpaceView],
)
async def update_space_chunking(
    tenant_id: str,
    space_id: str,
    payload: KnowledgeSpaceChunkingUpdateRequest,
    request: Request,
    authenticated: AuthenticatedSession = Depends(
        require_permission(KNOWLEDGE_SPACES_MANAGE, csrf=True)
    ),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[KnowledgeSpaceView]:
    return ok(
        await _service(request, session).update_space_chunking(
            authenticated.principal, tenant_id, space_id, payload
        ),
        get_request_id(request),
    )


@router.patch(
    "/tenants/{tenant_id}/knowledge/spaces/{space_id}/retrieval",
    response_model=ApiResponse[KnowledgeSpaceView],
)
async def update_space_retrieval(
    tenant_id: str,
    space_id: str,
    payload: KnowledgeSpaceRetrievalUpdateRequest,
    request: Request,
    authenticated: AuthenticatedSession = Depends(
        require_permission(KNOWLEDGE_SPACES_MANAGE, csrf=True)
    ),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[KnowledgeSpaceView]:
    return ok(
        await _service(request, session).update_space_retrieval(
            authenticated.principal, tenant_id, space_id, payload
        ),
        get_request_id(request),
    )


@router.get(
    "/tenants/{tenant_id}/knowledge/spaces/{space_id}/grants",
    response_model=ApiResponse[KnowledgeSpaceGrantsView],
)
async def get_space_grants(
    tenant_id: str,
    space_id: str,
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_permission(KNOWLEDGE_ACCESS_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[KnowledgeSpaceGrantsView]:
    return ok(
        await _service(request, session).get_grants(authenticated.principal, tenant_id, space_id),
        get_request_id(request),
    )


@router.put(
    "/tenants/{tenant_id}/knowledge/spaces/{space_id}/grants",
    response_model=ApiResponse[KnowledgeSpaceGrantsView],
)
async def replace_space_grants(
    tenant_id: str,
    space_id: str,
    payload: KnowledgeSpaceGrantsRequest,
    request: Request,
    authenticated: AuthenticatedSession = Depends(
        require_permission(KNOWLEDGE_ACCESS_MANAGE, csrf=True)
    ),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[KnowledgeSpaceGrantsView]:
    return ok(
        await _service(request, session).replace_grants(
            authenticated.principal, tenant_id, space_id, payload
        ),
        get_request_id(request),
    )


@router.get(
    "/tenants/{tenant_id}/knowledge/spaces/{space_id}/documents",
    response_model=ApiResponse[list[KnowledgeDocumentView]],
)
async def list_documents(
    tenant_id: str,
    space_id: str,
    request: Request,
    query: str | None = Query(default=None, max_length=300),
    authenticated: AuthenticatedSession = Depends(require_permission(KNOWLEDGE_DOCUMENTS_READ)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[list[KnowledgeDocumentView]]:
    return ok(
        await _service(request, session).list_documents(
            authenticated.principal, tenant_id, space_id, query=query
        ),
        get_request_id(request),
    )


@router.post(
    "/tenants/{tenant_id}/knowledge/spaces/{space_id}/documents",
    response_model=ApiResponse[KnowledgeDocumentView],
    status_code=201,
)
async def create_document(
    tenant_id: str,
    space_id: str,
    payload: KnowledgeDocumentCreateRequest,
    request: Request,
    authenticated: AuthenticatedSession = Depends(
        require_permission(KNOWLEDGE_DOCUMENTS_MANAGE, csrf=True)
    ),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[KnowledgeDocumentView]:
    return ok(
        await _service(request, session).create_document(
            authenticated.principal, tenant_id, space_id, payload
        ),
        get_request_id(request),
    )


@router.get(
    "/tenants/{tenant_id}/knowledge/citations/{citation_id}",
    response_model=ApiResponse[KnowledgeCitationView],
)
async def expand_citation(
    tenant_id: str,
    citation_id: str,
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_permission(KNOWLEDGE_QUERY)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[KnowledgeCitationView]:
    return ok(
        await _citation_service(request, session).expand(
            authenticated.principal, tenant_id, citation_id
        ),
        get_request_id(request),
    )


@router.get(
    "/tenants/{tenant_id}/knowledge/spaces/{space_id}/search",
    response_model=ApiResponse[list[KnowledgeSearchResult]],
)
async def search_space(
    tenant_id: str,
    space_id: str,
    request: Request,
    query: str = Query(min_length=1, max_length=1000),
    authenticated: AuthenticatedSession = Depends(require_permission(KNOWLEDGE_QUERY)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[list[KnowledgeSearchResult]]:
    data = await _service(request, session).search(
        authenticated.principal,
        tenant_id,
        space_id,
        query,
    )
    return ok(data, get_request_id(request))


@router.get(
    "/tenants/{tenant_id}/knowledge/spaces/{space_id}/agents",
    response_model=ApiResponse[KnowledgeSpaceAgentBindingsView],
)
async def get_space_agents(
    tenant_id: str,
    space_id: str,
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_permission(AGENTS_READ)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[KnowledgeSpaceAgentBindingsView]:
    return ok(
        await _service(request, session).get_space_agents(
            authenticated.principal, tenant_id, space_id
        ),
        get_request_id(request),
    )


@router.get(
    "/tenants/{tenant_id}/agents/{agent_id}/knowledge-spaces",
    response_model=ApiResponse[AgentKnowledgeSpaceBindingsView],
)
async def get_agent_spaces(
    tenant_id: str,
    agent_id: str,
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_permission(AGENTS_READ)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[AgentKnowledgeSpaceBindingsView]:
    return ok(
        await _service(request, session).get_agent_spaces(
            authenticated.principal, tenant_id, agent_id
        ),
        get_request_id(request),
    )


@router.post(
    "/tenants/{tenant_id}/agents/{agent_id}/knowledge-search-test",
    response_model=ApiResponse[AgentKnowledgeSearchTestView],
)
async def test_agent_knowledge_search(
    tenant_id: str,
    agent_id: str,
    payload: AgentKnowledgeSearchTestRequest,
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_permission(AGENTS_READ, csrf=True)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[AgentKnowledgeSearchTestView]:
    return ok(
        await _service(request, session).test_agent_search(
            authenticated.principal, tenant_id, agent_id, payload
        ),
        get_request_id(request),
    )


@router.put(
    "/tenants/{tenant_id}/agents/{agent_id}/knowledge-spaces",
    response_model=ApiResponse[AgentKnowledgeSpaceBindingsView],
)
async def replace_agent_spaces(
    tenant_id: str,
    agent_id: str,
    payload: AgentKnowledgeSpaceBindingsRequest,
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_permission(AGENTS_MANAGE, csrf=True)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[AgentKnowledgeSpaceBindingsView]:
    return ok(
        await _service(request, session).replace_agent_spaces(
            authenticated.principal, tenant_id, agent_id, payload.space_ids
        ),
        get_request_id(request),
    )


@router.post(
    "/tenants/{tenant_id}/agents/{agent_id}/knowledge-spaces/{space_id}",
    response_model=ApiResponse[AgentKnowledgeSpaceBindingsView],
)
async def add_agent_space(
    tenant_id: str,
    agent_id: str,
    space_id: str,
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_permission(AGENTS_MANAGE, csrf=True)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[AgentKnowledgeSpaceBindingsView]:
    return ok(
        await _service(request, session).add_agent_space(
            authenticated.principal, tenant_id, agent_id, space_id
        ),
        get_request_id(request),
    )


@router.delete(
    "/tenants/{tenant_id}/agents/{agent_id}/knowledge-spaces/{space_id}",
    response_model=ApiResponse[AgentKnowledgeSpaceBindingsView],
)
async def remove_agent_space(
    tenant_id: str,
    agent_id: str,
    space_id: str,
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_permission(AGENTS_MANAGE, csrf=True)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[AgentKnowledgeSpaceBindingsView]:
    return ok(
        await _service(request, session).remove_agent_space(
            authenticated.principal, tenant_id, agent_id, space_id
        ),
        get_request_id(request),
    )
