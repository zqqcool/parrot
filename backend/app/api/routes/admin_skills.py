from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session, require_permission
from app.core.request_id import get_request_id
from app.core.response import ApiResponse, ok
from app.infrastructure.skill_package_storage import LocalSkillPackageStorage
from app.modules.agents.skill_usage import AgentSkillUsage
from app.modules.iam.permissions import SKILLS_MANAGE, SKILLS_READ
from app.modules.iam.service import AuthenticatedSession
from app.modules.skills.build_service import SkillBuildService
from app.modules.skills.draft_entry_service import SkillDraftEntryService
from app.modules.skills.schemas import (
    SkillBuildView,
    SkillCreateRequest,
    SkillDraftDirectoryCreateRequest,
    SkillDraftEntryDeleteRequest,
    SkillDraftEntryMutationView,
    SkillDraftFileCreateRequest,
    SkillDraftFileWriteRequest,
    SkillDraftForkRequest,
    SkillFileContentView,
    SkillFileView,
    SkillRollbackRequest,
    SkillUpdateRequest,
    SkillVersionView,
    SkillView,
)
from app.modules.skills.service import SkillService
from app.modules.skills.version_service import SkillVersionService

router = APIRouter()
SkillPackageFile = Annotated[UploadFile, File(...)]


def _service(request: Request, session: AsyncSession) -> SkillService:
    settings = request.app.state.settings
    agent_skill_usage = AgentSkillUsage(session)
    return SkillService(
        session,
        request.app.state.database,
        LocalSkillPackageStorage(settings.skills.package_directory),
        settings.skills.max_package_bytes,
        deletion_guard=agent_skill_usage,
        bound_agent_reader=agent_skill_usage,
        dispatcher=request.app.state.task_dispatcher,
    )


def _version_service(request: Request, session: AsyncSession) -> SkillVersionService:
    settings = request.app.state.settings
    return SkillVersionService(
        session,
        request.app.state.database,
        LocalSkillPackageStorage(settings.skills.package_directory),
        settings.skills.max_package_bytes,
        bound_agent_reader=AgentSkillUsage(session),
        dispatcher=request.app.state.task_dispatcher,
    )


def _draft_entries(request: Request, session: AsyncSession) -> SkillDraftEntryService:
    settings = request.app.state.settings
    return SkillDraftEntryService(
        session,
        request.app.state.database,
        LocalSkillPackageStorage(settings.skills.package_directory),
        settings.skills.max_package_bytes,
    )


def _build_service(request: Request, session: AsyncSession) -> SkillBuildService:
    return SkillBuildService(
        session, request.app.state.database, request.app.state.task_dispatcher
    )


@router.get("/tenants/{tenant_id}/skills", response_model=ApiResponse[list[SkillView]])
async def list_skills(
    tenant_id: str,
    request: Request,
    query: str | None = Query(default=None, max_length=300),
    authenticated: AuthenticatedSession = Depends(require_permission(SKILLS_READ)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[list[SkillView]]:
    data = await _service(request, session).list(authenticated.principal, tenant_id, query=query)
    return ok(data, get_request_id(request))


@router.post("/tenants/{tenant_id}/skills", response_model=ApiResponse[SkillView], status_code=201)
async def create_skill(
    tenant_id: str,
    payload: SkillCreateRequest,
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_permission(SKILLS_MANAGE, csrf=True)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[SkillView]:
    data = await _service(request, session).create(authenticated.principal, tenant_id, payload)
    return ok(data, get_request_id(request))


@router.post(
    "/tenants/{tenant_id}/skills/import",
    response_model=ApiResponse[SkillView],
    status_code=201,
)
async def import_skill(
    tenant_id: str,
    request: Request,
    file: SkillPackageFile,
    authenticated: AuthenticatedSession = Depends(require_permission(SKILLS_MANAGE, csrf=True)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[SkillView]:
    max_package_bytes = request.app.state.settings.skills.max_package_bytes
    try:
        content = await file.read(max_package_bytes + 1)
    finally:
        await file.close()
    data = await _version_service(request, session).import_package(
        authenticated.principal, tenant_id, file.filename or "", content
    )
    return ok(data, get_request_id(request))


@router.patch("/tenants/{tenant_id}/skills/{skill_id}", response_model=ApiResponse[SkillView])
async def update_skill(
    tenant_id: str,
    skill_id: str,
    payload: SkillUpdateRequest,
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_permission(SKILLS_MANAGE, csrf=True)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[SkillView]:
    if payload.status == "published":
        data = await _version_service(request, session).publish(
            authenticated.principal, tenant_id, skill_id
        )
        return ok(data, get_request_id(request))
    data = await _service(request, session).update(
        authenticated.principal, tenant_id, skill_id, payload
    )
    return ok(data, get_request_id(request))


@router.delete(
    "/tenants/{tenant_id}/skills/{skill_id}", response_model=ApiResponse[dict[str, bool]]
)
async def delete_skill(
    tenant_id: str,
    skill_id: str,
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_permission(SKILLS_MANAGE, csrf=True)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[dict[str, bool]]:
    await _service(request, session).delete(authenticated.principal, tenant_id, skill_id)
    return ok({"deleted": True}, get_request_id(request))


@router.get(
    "/tenants/{tenant_id}/skills/{skill_id}/versions",
    response_model=ApiResponse[list[SkillVersionView]],
)
async def list_skill_versions(
    tenant_id: str,
    skill_id: str,
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_permission(SKILLS_READ)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[list[SkillVersionView]]:
    data = await _version_service(request, session).list_versions(
        authenticated.principal, tenant_id, skill_id
    )
    return ok(data, get_request_id(request))


@router.post(
    "/tenants/{tenant_id}/skills/{skill_id}/draft:fork",
    response_model=ApiResponse[SkillVersionView],
)
async def fork_skill_draft(
    tenant_id: str,
    skill_id: str,
    payload: SkillDraftForkRequest,
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_permission(SKILLS_MANAGE, csrf=True)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[SkillVersionView]:
    data = await _version_service(request, session).fork_draft(
        authenticated.principal, tenant_id, skill_id, payload.source_version_id
    )
    return ok(data, get_request_id(request))


@router.post(
    "/tenants/{tenant_id}/skills/{skill_id}/draft:build",
    response_model=ApiResponse[SkillBuildView],
)
async def build_skill_draft(
    tenant_id: str,
    skill_id: str,
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_permission(SKILLS_MANAGE, csrf=True)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[SkillBuildView]:
    data = await _build_service(request, session).request(
        authenticated.principal, tenant_id, skill_id
    )
    return ok(data, get_request_id(request))


@router.get(
    "/tenants/{tenant_id}/skills/{skill_id}/draft/build",
    response_model=ApiResponse[SkillBuildView | None],
)
async def get_skill_draft_build(
    tenant_id: str,
    skill_id: str,
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_permission(SKILLS_READ)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[SkillBuildView | None]:
    data = await _build_service(request, session).get(authenticated.principal, tenant_id, skill_id)
    return ok(data, get_request_id(request))


@router.post(
    "/tenants/{tenant_id}/skills/{skill_id}:publish",
    response_model=ApiResponse[SkillView],
)
async def publish_skill(
    tenant_id: str,
    skill_id: str,
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_permission(SKILLS_MANAGE, csrf=True)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[SkillView]:
    data = await _version_service(request, session).publish(
        authenticated.principal, tenant_id, skill_id
    )
    return ok(data, get_request_id(request))


@router.post(
    "/tenants/{tenant_id}/skills/{skill_id}:rollback",
    response_model=ApiResponse[SkillView],
)
async def rollback_skill(
    tenant_id: str,
    skill_id: str,
    payload: SkillRollbackRequest,
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_permission(SKILLS_MANAGE, csrf=True)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[SkillView]:
    data = await _version_service(request, session).rollback(
        authenticated.principal, tenant_id, skill_id, payload.version_id
    )
    return ok(data, get_request_id(request))


@router.get(
    "/tenants/{tenant_id}/skills/{skill_id}/versions/{version_id}/files",
    response_model=ApiResponse[list[SkillFileView]],
)
async def list_skill_version_files(
    tenant_id: str,
    skill_id: str,
    version_id: str,
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_permission(SKILLS_READ)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[list[SkillFileView]]:
    data = await _version_service(request, session).list_files(
        authenticated.principal, tenant_id, skill_id, version_id
    )
    return ok(data, get_request_id(request))


@router.get(
    "/tenants/{tenant_id}/skills/{skill_id}/versions/{version_id}/files/content",
    response_model=ApiResponse[SkillFileContentView],
)
async def get_skill_version_file(
    tenant_id: str,
    skill_id: str,
    version_id: str,
    request: Request,
    path: str = Query(min_length=1, max_length=512),
    authenticated: AuthenticatedSession = Depends(require_permission(SKILLS_READ)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[SkillFileContentView]:
    data = await _version_service(request, session).read_file(
        authenticated.principal, tenant_id, skill_id, version_id, path
    )
    return ok(data, get_request_id(request))


@router.put(
    "/tenants/{tenant_id}/skills/{skill_id}/draft/files/content",
    response_model=ApiResponse[SkillFileContentView],
)
async def write_skill_draft_file(
    tenant_id: str,
    skill_id: str,
    payload: SkillDraftFileWriteRequest,
    request: Request,
    path: str = Query(min_length=1, max_length=512),
    authenticated: AuthenticatedSession = Depends(require_permission(SKILLS_MANAGE, csrf=True)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[SkillFileContentView]:
    data = await _version_service(request, session).write_draft_file(
        authenticated.principal,
        tenant_id,
        skill_id,
        path,
        payload.content,
        payload.expected_checksum,
    )
    return ok(data, get_request_id(request))


@router.post(
    "/tenants/{tenant_id}/skills/{skill_id}/draft/files",
    response_model=ApiResponse[SkillDraftEntryMutationView],
)
async def create_skill_draft_file(
    tenant_id: str,
    skill_id: str,
    payload: SkillDraftFileCreateRequest,
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_permission(SKILLS_MANAGE, csrf=True)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[SkillDraftEntryMutationView]:
    data = await _draft_entries(request, session).create_file(
        authenticated.principal,
        tenant_id,
        skill_id,
        payload.path,
        payload.content,
        payload.expected_checksum,
    )
    return ok(data, get_request_id(request))


@router.post(
    "/tenants/{tenant_id}/skills/{skill_id}/draft/directories",
    response_model=ApiResponse[SkillDraftEntryMutationView],
)
async def create_skill_draft_directory(
    tenant_id: str,
    skill_id: str,
    payload: SkillDraftDirectoryCreateRequest,
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_permission(SKILLS_MANAGE, csrf=True)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[SkillDraftEntryMutationView]:
    data = await _draft_entries(request, session).create_directory(
        authenticated.principal, tenant_id, skill_id, payload.path, payload.expected_checksum
    )
    return ok(data, get_request_id(request))


@router.delete(
    "/tenants/{tenant_id}/skills/{skill_id}/draft/entries",
    response_model=ApiResponse[SkillDraftEntryMutationView],
)
async def delete_skill_draft_entry(
    tenant_id: str,
    skill_id: str,
    payload: SkillDraftEntryDeleteRequest,
    request: Request,
    authenticated: AuthenticatedSession = Depends(require_permission(SKILLS_MANAGE, csrf=True)),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[SkillDraftEntryMutationView]:
    data = await _draft_entries(request, session).delete(
        authenticated.principal, tenant_id, skill_id, payload.path, payload.expected_checksum
    )
    return ok(data, get_request_id(request))
