from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session, require_permission
from app.core.object_storage import ObjectUploadGrant
from app.core.request_id import get_request_id
from app.core.response import ApiResponse, ok
from app.modules.iam.permissions import KNOWLEDGE_DOCUMENTS_MANAGE, KNOWLEDGE_DOCUMENTS_READ
from app.modules.iam.service import AuthenticatedSession
from app.modules.knowledge.ingestion_service import KnowledgeIngestionService
from app.modules.knowledge.lifecycle_service import KnowledgeDocumentLifecycleService
from app.modules.knowledge.schemas import (
    KnowledgeDocumentChunkPageView,
    KnowledgeDocumentTextVersionCreateRequest,
    KnowledgeDocumentVersionUploadRequest,
    KnowledgeDocumentVersionView,
    KnowledgeDocumentView,
    KnowledgeIngestionView,
    KnowledgeSourceActivityPageView,
    KnowledgeSourceConfirmRequest,
    KnowledgeSourceUploadGrantView,
    KnowledgeSourceUploadRequest,
)
from app.modules.knowledge.source_activity_service import KnowledgeSourceActivityService
from app.modules.knowledge.text_version_service import KnowledgeDocumentTextVersionService

router = APIRouter()


def content_disposition(disposition: str, filename: str) -> str:
    """Build a Content-Disposition that stays proxy-friendly for ASCII names.

    Prefer a quoted ``filename=`` when the basename is ASCII-safe so local Vite
    / http-proxy does not choke on ``filename*=UTF-8''`` while rewriting binary
    responses. Fall back to RFC 5987 encoding for non-ASCII names.
    """
    safe = filename.replace("\\", "/").rsplit("/", 1)[-1].strip() or "download"
    if safe.isascii() and all(32 <= ord(ch) < 127 and ch not in {"\\", '"'} for ch in safe):
        return f'{disposition}; filename="{safe}"'
    return f"{disposition}; filename*=UTF-8''{quote(safe)}"


def _ingestion_service(request: Request, session: AsyncSession) -> KnowledgeIngestionService:
    return KnowledgeIngestionService(
        session,
        request.app.state.database,
        request.app.state.object_storage,
        request.app.state.settings.knowledge.max_upload_bytes,
        request.app.state.task_dispatcher,
    )


def _lifecycle_service(
    request: Request, session: AsyncSession
) -> KnowledgeDocumentLifecycleService:
    return KnowledgeDocumentLifecycleService(
        session,
        request.app.state.database,
        request.app.state.object_storage,
        request.app.state.task_dispatcher,
    )


def _text_version_service(
    request: Request, session: AsyncSession
) -> KnowledgeDocumentTextVersionService:
    return KnowledgeDocumentTextVersionService(
        session, request.app.state.database, request.app.state.task_dispatcher
    )


@router.get(
    "/tenants/{tenant_id}/knowledge/spaces/{space_id}/sources",
    response_model=ApiResponse[KnowledgeSourceActivityPageView],
)
async def list_knowledge_sources(
    tenant_id: str,
    space_id: str,
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    authenticated: AuthenticatedSession = Depends(require_permission(KNOWLEDGE_DOCUMENTS_READ)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[KnowledgeSourceActivityPageView]:
    data = await KnowledgeSourceActivityService(
        session,
        request.app.state.database,
        request.app.state.settings.knowledge.staging_retention_hours,
    ).list_for_space(
        authenticated.principal,
        tenant_id,
        space_id,
        page=page,
        page_size=page_size,
    )
    return ok(data, get_request_id(request))


@router.post(
    "/tenants/{tenant_id}/knowledge/spaces/{space_id}/document-upload-grants",
    response_model=ApiResponse[KnowledgeSourceUploadGrantView],
    status_code=201,
)
async def issue_document_upload(
    tenant_id: str,
    space_id: str,
    payload: KnowledgeSourceUploadRequest,
    request: Request,
    authenticated: AuthenticatedSession = Depends(
        require_permission(KNOWLEDGE_DOCUMENTS_MANAGE, csrf=True)
    ),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[KnowledgeSourceUploadGrantView]:
    source, grant = await _ingestion_service(request, session).issue_upload(
        authenticated.principal, tenant_id, space_id, payload
    )
    return ok(_upload_grant(source.id, grant), get_request_id(request))


@router.post(
    "/tenants/{tenant_id}/knowledge/documents/{document_id}/version-upload-grants",
    response_model=ApiResponse[KnowledgeSourceUploadGrantView],
    status_code=201,
)
async def issue_document_version_upload(
    tenant_id: str,
    document_id: str,
    payload: KnowledgeDocumentVersionUploadRequest,
    request: Request,
    authenticated: AuthenticatedSession = Depends(
        require_permission(KNOWLEDGE_DOCUMENTS_MANAGE, csrf=True)
    ),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[KnowledgeSourceUploadGrantView]:
    source, grant = await _ingestion_service(request, session).issue_replacement_upload(
        authenticated.principal, tenant_id, document_id, payload
    )
    return ok(_upload_grant(source.id, grant), get_request_id(request))


@router.post(
    "/tenants/{tenant_id}/knowledge/documents/{document_id}/text-versions",
    response_model=ApiResponse[KnowledgeDocumentView],
    status_code=201,
)
async def create_document_text_version(
    tenant_id: str,
    document_id: str,
    payload: KnowledgeDocumentTextVersionCreateRequest,
    request: Request,
    authenticated: AuthenticatedSession = Depends(
        require_permission(KNOWLEDGE_DOCUMENTS_MANAGE, csrf=True)
    ),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[KnowledgeDocumentView]:
    return ok(
        await _text_version_service(request, session).replace(
            authenticated.principal, tenant_id, document_id, payload
        ),
        get_request_id(request),
    )


def _upload_grant(source_id: str, grant: ObjectUploadGrant) -> KnowledgeSourceUploadGrantView:
    return KnowledgeSourceUploadGrantView(
        source_id=source_id,
        object_key=grant.object_key,
        upload_key=grant.upload_key,
        upload_token=grant.upload_token,
        expires_at=grant.expires_at,
    )


@router.post(
    "/tenants/{tenant_id}/knowledge/sources/{source_id}/confirm",
    response_model=ApiResponse[KnowledgeIngestionView],
    status_code=202,
)
async def confirm_document_upload(
    tenant_id: str,
    source_id: str,
    payload: KnowledgeSourceConfirmRequest,
    request: Request,
    authenticated: AuthenticatedSession = Depends(
        require_permission(KNOWLEDGE_DOCUMENTS_MANAGE, csrf=True)
    ),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[KnowledgeIngestionView]:
    return ok(
        await _ingestion_service(request, session).confirm_upload(
            authenticated.principal, tenant_id, source_id, payload
        ),
        get_request_id(request),
    )


@router.post(
    "/tenants/{tenant_id}/knowledge/sources/{source_id}/retry-confirm",
    response_model=ApiResponse[KnowledgeIngestionView],
    status_code=202,
)
async def retry_document_upload_confirmation(
    tenant_id: str,
    source_id: str,
    request: Request,
    authenticated: AuthenticatedSession = Depends(
        require_permission(KNOWLEDGE_DOCUMENTS_MANAGE, csrf=True)
    ),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[KnowledgeIngestionView]:
    return ok(
        await _ingestion_service(request, session).retry_upload_confirmation(
            authenticated.principal, tenant_id, source_id
        ),
        get_request_id(request),
    )


@router.delete(
    "/tenants/{tenant_id}/knowledge/sources/{source_id}",
    response_model=ApiResponse[None],
)
async def cleanup_staging_document_upload(
    tenant_id: str,
    source_id: str,
    request: Request,
    authenticated: AuthenticatedSession = Depends(
        require_permission(KNOWLEDGE_DOCUMENTS_MANAGE, csrf=True)
    ),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[None]:
    await _ingestion_service(request, session).cleanup_staging_source(
        authenticated.principal, tenant_id, source_id
    )
    return ok(None, get_request_id(request))


@router.get(
    "/tenants/{tenant_id}/knowledge/spaces/{space_id}/ingestions",
    response_model=ApiResponse[list[KnowledgeIngestionView]],
)
async def list_active_ingestions(
    tenant_id: str,
    space_id: str,
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_permission(KNOWLEDGE_DOCUMENTS_READ)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[list[KnowledgeIngestionView]]:
    data = await _ingestion_service(request, session).list_active_jobs(
        authenticated.principal, tenant_id, space_id
    )
    return ok(list(data), get_request_id(request))


@router.get(
    "/tenants/{tenant_id}/knowledge/ingestions/{job_id}",
    response_model=ApiResponse[KnowledgeIngestionView],
)
async def get_ingestion(
    tenant_id: str,
    job_id: str,
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_permission(KNOWLEDGE_DOCUMENTS_READ)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[KnowledgeIngestionView]:
    return ok(
        await _ingestion_service(request, session).get_job(
            authenticated.principal, tenant_id, job_id
        ),
        get_request_id(request),
    )


@router.get(
    "/tenants/{tenant_id}/knowledge/documents/{document_id}/versions",
    response_model=ApiResponse[list[KnowledgeDocumentVersionView]],
)
async def list_document_versions(
    tenant_id: str,
    document_id: str,
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_permission(KNOWLEDGE_DOCUMENTS_READ)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[list[KnowledgeDocumentVersionView]]:
    data = await _lifecycle_service(request, session).list_versions(
        authenticated.principal, tenant_id, document_id
    )
    return ok(list(data), get_request_id(request))


@router.get(
    "/tenants/{tenant_id}/knowledge/documents/{document_id}/versions/{version_id}/chunks",
    response_model=ApiResponse[KnowledgeDocumentChunkPageView],
)
async def list_document_version_chunks(
    tenant_id: str,
    document_id: str,
    version_id: str,
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    authenticated: AuthenticatedSession = Depends(require_permission(KNOWLEDGE_DOCUMENTS_READ)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[KnowledgeDocumentChunkPageView]:
    data = await _lifecycle_service(request, session).list_chunks(
        authenticated.principal,
        tenant_id,
        document_id,
        version_id,
        page=page,
        page_size=page_size,
    )
    return ok(data, get_request_id(request))


@router.get(
    "/tenants/{tenant_id}/knowledge/documents/{document_id}/versions/{version_id}/source",
    response_class=Response,
)
async def download_document_version_source(
    tenant_id: str,
    document_id: str,
    version_id: str,
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_permission(KNOWLEDGE_DOCUMENTS_READ)),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    source = await _lifecycle_service(request, session).source_file(
        authenticated.principal, tenant_id, document_id, version_id
    )
    return Response(
        content=source.content,
        media_type=source.content_type,
        headers={
            "Content-Disposition": content_disposition("attachment", source.filename),
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get(
    "/tenants/{tenant_id}/knowledge/media/{asset_id}/content",
    response_class=Response,
)
async def download_knowledge_media(
    tenant_id: str,
    asset_id: str,
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_permission(KNOWLEDGE_DOCUMENTS_READ)),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    media = await _lifecycle_service(request, session).media_file(
        authenticated.principal, tenant_id, asset_id
    )
    return Response(
        content=media.content,
        media_type=media.content_type,
        headers={
            "Content-Disposition": content_disposition("inline", media.filename),
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post(
    "/tenants/{tenant_id}/knowledge/documents/{document_id}/archive",
    response_model=ApiResponse[None],
)
async def archive_document(
    tenant_id: str,
    document_id: str,
    request: Request,
    authenticated: AuthenticatedSession = Depends(
        require_permission(KNOWLEDGE_DOCUMENTS_MANAGE, csrf=True)
    ),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[None]:
    await _lifecycle_service(request, session).archive(
        authenticated.principal, tenant_id, document_id
    )
    return ok(None, get_request_id(request))
