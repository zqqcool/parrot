from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.avatar_validation import (
    ValidatedAvatar,
    validate_avatar,
    validate_avatar_upload_metadata,
)
from app.core.errors import AppError
from app.core.ids import new_id
from app.core.object_storage import ObjectData, ObjectStoragePort, ObjectUploadGrant
from app.infrastructure.db.session import DatabaseManager
from app.modules.audit.service import append_audit
from app.modules.iam.models import User
from app.modules.iam.permissions import PLATFORM_TENANTS_MANAGE
from app.modules.iam.repository import IamRepository
from app.modules.iam.schemas import PrincipalContext

logger = logging.getLogger(__name__)


class TenantUserAvatarService:
    def __init__(
        self,
        session: AsyncSession,
        database: DatabaseManager,
        object_storage: ObjectStoragePort,
        max_avatar_bytes: int,
    ) -> None:
        self.session = session
        self.database = database
        self.object_storage = object_storage
        self.max_avatar_bytes = max_avatar_bytes
        self.iam = IamRepository(session)

    async def issue_upload(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        user_id: str,
        content_type: str,
        size_bytes: int,
    ) -> ObjectUploadGrant:
        await self._enter_tenant(principal, tenant_id, "tenant.users.manage")
        await self._get_tenant_user(tenant_id, user_id)
        validate_avatar_upload_metadata(content_type, size_bytes, self.max_avatar_bytes)
        staging_key = f"staging/user-avatars/{tenant_id}/{user_id}/{new_id('upload')}"
        return await self.object_storage.issue_upload_grant(staging_key, content_type, size_bytes)

    async def attach(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        user_id: str,
        staging_key: str,
    ) -> bool:
        await self._enter_tenant(principal, tenant_id, "tenant.users.manage")
        user = await self._get_tenant_user(tenant_id, user_id)
        self._validate_staging_key(tenant_id, user_id, staging_key)
        staged_object = await self._read_staged_avatar(staging_key)
        avatar = validate_avatar(
            staged_object.content,
            staged_object.content_type,
            self.max_avatar_bytes,
        )
        return await self._persist_avatar(principal, tenant_id, user, staging_key, avatar)

    async def issue_self_upload(
        self,
        principal: PrincipalContext,
        content_type: str,
        size_bytes: int,
    ) -> ObjectUploadGrant:
        tenant_id = await self._enter_self_tenant(principal)
        await self._get_tenant_user(tenant_id, principal.subject_id)
        validate_avatar_upload_metadata(content_type, size_bytes, self.max_avatar_bytes)
        staging_key = f"staging/user-avatars/{tenant_id}/{principal.subject_id}/{new_id('upload')}"
        return await self.object_storage.issue_upload_grant(staging_key, content_type, size_bytes)

    async def attach_self(self, principal: PrincipalContext, staging_key: str) -> bool:
        tenant_id = await self._enter_self_tenant(principal)
        user = await self._get_tenant_user(tenant_id, principal.subject_id)
        self._validate_staging_key(tenant_id, principal.subject_id, staging_key)
        staged_object = await self._read_staged_avatar(staging_key)
        avatar = validate_avatar(
            staged_object.content,
            staged_object.content_type,
            self.max_avatar_bytes,
        )
        return await self._persist_avatar(principal, tenant_id, user, staging_key, avatar)

    async def get_self(self, principal: PrincipalContext) -> tuple[bytes, str]:
        tenant_id = await self._enter_self_tenant(principal)
        return await self._read_avatar(await self._get_tenant_user(tenant_id, principal.subject_id))

    async def get(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        user_id: str,
    ) -> tuple[bytes, str]:
        await self._enter_tenant(principal, tenant_id, "tenant.users.read")
        user = await self._get_tenant_user(tenant_id, user_id)
        return await self._read_avatar(user)

    async def _read_avatar(self, user: User) -> tuple[bytes, str]:
        if not user.avatar_key or not user.avatar_content_type:
            raise AppError(
                "RESOURCE_NOT_FOUND",
                "User avatar not found",
                status.HTTP_404_NOT_FOUND,
            )
        stored_object = await self.object_storage.read(user.avatar_key)
        if stored_object is None:
            logger.error("User avatar object is missing", extra={"user_id": user.id})
            raise AppError(
                "RESOURCE_NOT_FOUND",
                "User avatar not found",
                status.HTTP_404_NOT_FOUND,
            )
        return stored_object.content, user.avatar_content_type

    async def _read_staged_avatar(self, staging_key: str) -> ObjectData:
        staged_object = await self.object_storage.read(staging_key)
        if staged_object is None:
            raise AppError(
                "AVATAR_UPLOAD_NOT_FOUND",
                "Avatar upload was not found or has expired",
                status.HTTP_404_NOT_FOUND,
            )
        return staged_object

    async def _persist_avatar(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        user: User,
        staging_key: str,
        avatar: ValidatedAvatar,
    ) -> bool:
        key = f"avatars/users/{user.id}/{new_id('avatar')}.{avatar.extension}"
        old_key = user.avatar_key
        try:
            await self.object_storage.write(key, avatar.content, avatar.content_type)
            user.avatar_key = key
            user.avatar_content_type = avatar.content_type
            await self.session.flush()
            append_audit(
                self.session,
                principal,
                "user.avatar.attach",
                "user",
                user.id,
                {"content_type": avatar.content_type, "size_bytes": len(avatar.content)},
                tenant_id=tenant_id,
            )
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            await self._delete_object(key)
            raise
        await self._delete_object(staging_key)
        await self._delete_object(old_key)
        return True

    async def _get_tenant_user(self, tenant_id: str, user_id: str) -> User:
        if await self.iam.get_membership(user_id, tenant_id) is None:
            raise AppError("RESOURCE_NOT_FOUND", "User not found", status.HTTP_404_NOT_FOUND)
        user = await self.iam.get_user(user_id)
        if user is None:
            raise AppError("RESOURCE_NOT_FOUND", "User not found", status.HTTP_404_NOT_FOUND)
        return user

    async def _enter_tenant(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        permission: str,
    ) -> None:
        if (
            principal.tenant_id != tenant_id
            and PLATFORM_TENANTS_MANAGE not in principal.permissions
        ):
            raise AppError("RESOURCE_NOT_FOUND", "User not found", status.HTTP_404_NOT_FOUND)
        if permission not in principal.permissions:
            raise AppError("FORBIDDEN", "Permission denied", status.HTTP_403_FORBIDDEN)
        await self.database.set_tenant(self.session, tenant_id)

    async def _enter_self_tenant(self, principal: PrincipalContext) -> str:
        tenant_id = principal.tenant_id
        if tenant_id is None:
            raise AppError(
                "TENANT_CONTEXT_REQUIRED",
                "An active tenant is required to manage an avatar",
                status.HTTP_409_CONFLICT,
            )
        if await self.iam.get_membership(principal.subject_id, tenant_id) is None:
            raise AppError("RESOURCE_NOT_FOUND", "User not found", status.HTTP_404_NOT_FOUND)
        await self.database.set_tenant(self.session, tenant_id)
        return tenant_id

    async def _delete_object(self, key: str | None) -> None:
        if not key:
            return
        try:
            await self.object_storage.delete(key)
        except Exception:
            logger.warning("Unable to delete user avatar object", extra={"avatar_key": key})

    @staticmethod
    def _validate_staging_key(tenant_id: str, user_id: str, staging_key: str) -> None:
        prefix = f"staging/user-avatars/{tenant_id}/{user_id}/upload_"
        if not staging_key.startswith(prefix) or "/" in staging_key[len(prefix) :]:
            raise AppError(
                "AVATAR_UPLOAD_INVALID",
                "Avatar upload does not belong to this user",
                status.HTTP_422_UNPROCESSABLE_CONTENT,
            )
