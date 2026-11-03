from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import cast
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.errors import AppError
from app.core.ids import new_id
from app.infrastructure.db.session import DatabaseManager
from app.modules.audit.models import AuditLog
from app.modules.audit.schemas import AuditView
from app.modules.iam.permissions import AUDIT_READ, PLATFORM_TENANTS_MANAGE
from app.modules.iam.schemas import PrincipalContext
from app.modules.iam.user_references import UserReferenceResolver

_UNSET = object()


class AuditQueryService:
    def __init__(self, session: AsyncSession, database: DatabaseManager) -> None:
        self.session = session
        self.database = database

    async def list(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        *,
        query: str | None = None,
        limit: int = 100,
    ) -> list[AuditView]:
        if (
            principal.tenant_id != tenant_id
            and PLATFORM_TENANTS_MANAGE not in principal.permissions
        ):
            raise AppError("RESOURCE_NOT_FOUND", "Resource not found", status.HTTP_404_NOT_FOUND)
        if AUDIT_READ not in principal.permissions:
            raise AppError("FORBIDDEN", "Permission denied", status.HTTP_403_FORBIDDEN)
        await self.database.set_tenant(self.session, tenant_id)
        statement = select(AuditLog).where(AuditLog.tenant_id == tenant_id)
        normalized = query.strip() if query else ""
        if normalized:
            statement = statement.where(
                or_(
                    AuditLog.action.icontains(normalized, autoescape=True),
                    AuditLog.resource_type.icontains(normalized, autoescape=True),
                    AuditLog.resource_id.icontains(normalized, autoescape=True),
                    AuditLog.request_id.icontains(normalized, autoescape=True),
                )
            )
        rows = list(
            await self.session.scalars(statement.order_by(AuditLog.created_at.desc()).limit(limit))
        )
        users = await UserReferenceResolver(self.session).resolve(
            tenant_id, (item.actor_id for item in rows if item.actor_type == "user")
        )
        return [
            AuditView(
                id=item.id,
                action=item.action,
                resource_type=item.resource_type,
                resource_id=item.resource_id,
                actor_type=item.actor_type,
                actor=users.get(item.actor_id) if item.actor_type == "user" else None,
                request_id=item.request_id,
                created_at=item.created_at.isoformat(),
            )
            for item in rows
        ]


def append_audit(
    session: AsyncSession,
    principal: PrincipalContext,
    action: str,
    resource_type: str,
    resource_id: str | None,
    metadata: dict[str, object] | None = None,
    *,
    tenant_id: str | None | object = _UNSET,
) -> None:
    resolved_tenant_id = principal.tenant_id if tenant_id is _UNSET else cast(str | None, tenant_id)
    session.add(
        AuditLog(
            id=new_id("audit"),
            tenant_id=resolved_tenant_id,
            actor_type=principal.subject_type,
            actor_id=principal.subject_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            request_id=principal.request_id,
            metadata_json=_json_metadata(metadata),
        )
    )


def _json_metadata(metadata: dict[str, object] | None) -> dict[str, object]:
    return {key: _json_safe(value) for key, value in (metadata or {}).items()}


def _json_safe(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Enum):
        return _json_safe(value.value)
    if isinstance(value, (Decimal, UUID)):
        return str(value)
    if isinstance(value, Mapping):
        mapping = cast(Mapping[object, object], value)
        return {str(key): _json_safe(item) for key, item in mapping.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        items = cast(Iterable[object], value)
        return [_json_safe(item) for item in items]
    raise TypeError(f"Unsupported audit metadata type: {type(value).__name__}")
