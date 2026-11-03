from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.api.dependencies import get_db_session
from app.core.errors import AppError
from app.modules.anonymous.service import AnonymousSessionService
from app.modules.knowledge.interaction_media_service import InteractionKnowledgeMediaService

router = APIRouter()


@router.get(
    "/interactions/{interaction_id}/knowledge/media/{asset_id}/content",
    response_class=Response,
)
async def download_interaction_knowledge_media(
    interaction_id: str,
    asset_id: str,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    visitor = await AnonymousSessionService(
        session,
        request.app.state.settings,
        request.app.state.database,
    ).authenticate(request.cookies.get(request.app.state.settings.security.visitor_cookie_name))
    if visitor is None:
        raise AppError(
            "UNAUTHORIZED",
            "Visitor session is required",
            status.HTTP_401_UNAUTHORIZED,
        )
    media = await InteractionKnowledgeMediaService(
        session,
        request.app.state.database,
        request.app.state.object_storage,
    ).download(
        tenant_id=visitor.tenant_id,
        actor_type="anonymous",
        actor_id=visitor.id,
        interaction_id=interaction_id,
        asset_id=asset_id,
    )
    return Response(
        content=media.content,
        media_type=media.content_type,
        headers={
            "Content-Disposition": _content_disposition("inline", media.filename),
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


def _content_disposition(disposition: str, filename: str) -> str:
    safe = filename.replace("\\", "/").rsplit("/", 1)[-1].strip() or "download"
    if safe.isascii() and all(32 <= ord(ch) < 127 and ch not in {"\\", '"'} for ch in safe):
        return f'{disposition}; filename="{safe}"'
    return f"{disposition}; filename*=UTF-8''{quote(safe)}"
