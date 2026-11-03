from datetime import UTC, datetime, timedelta
from io import BytesIO
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock

import pytest
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.object_storage import ObjectData, ObjectStoragePort, ObjectUploadGrant
from app.infrastructure.db.session import DatabaseManager
from app.modules.iam.schemas import PrincipalContext
from app.modules.tenancy.user_avatar_service import TenantUserAvatarService


class InMemoryObjectStorage:
    def __init__(self) -> None:
        self.objects: dict[str, ObjectData] = {}
        self.deleted: list[str] = []

    async def issue_upload_grant(
        self, key: str, content_type: str, size_bytes: int
    ) -> ObjectUploadGrant:
        return ObjectUploadGrant(
            object_key=key,
            upload_key=f"parrot/{key}",
            upload_token="upload-token",
            expires_at=datetime.now(UTC) + timedelta(minutes=15),
        )

    async def write(self, key: str, content: bytes, content_type: str) -> None:
        self.objects[key] = ObjectData(content=content, content_type=content_type)

    async def read(self, key: str) -> ObjectData | None:
        return self.objects.get(key)

    async def delete(self, key: str) -> None:
        self.deleted.append(key)
        self.objects.pop(key, None)


def _image_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (1, 1), "white").save(output, format="PNG")
    return output.getvalue()


def _principal() -> PrincipalContext:
    return PrincipalContext(
        tenant_id="tenant_test",
        subject_id="admin_test",
        username="admin",
        display_name="Admin",
        permissions=("tenant.users.manage", "tenant.users.read"),
        tenants=(),
        must_change_password=False,
        request_id="req_test",
    )


def _service(
    storage: InMemoryObjectStorage,
) -> tuple[TenantUserAvatarService, SimpleNamespace, SimpleNamespace]:
    user = SimpleNamespace(
        id="user_test",
        avatar_key="avatars/users/user_test/previous.png",
        avatar_content_type="image/png",
    )
    session = SimpleNamespace(
        flush=AsyncMock(),
        commit=AsyncMock(),
        rollback=AsyncMock(),
        add=Mock(),
    )
    service = TenantUserAvatarService(
        cast(AsyncSession, session),
        cast(DatabaseManager, SimpleNamespace(set_tenant=AsyncMock())),
        cast(ObjectStoragePort, storage),
        2 * 1024 * 1024,
    )
    mocked_service = cast(Any, service)
    mocked_service._enter_tenant = AsyncMock()
    mocked_service._get_tenant_user = AsyncMock(return_value=user)
    return service, user, session


@pytest.mark.asyncio
async def test_user_avatar_upload_grant_is_scoped_to_tenant_membership() -> None:
    storage = InMemoryObjectStorage()
    service, _, _ = _service(storage)

    grant = await service.issue_upload(
        _principal(), "tenant_test", "user_test", "image/png", len(_image_bytes())
    )

    assert grant.object_key.startswith("staging/user-avatars/tenant_test/user_test/upload_")
    assert grant.upload_token == "upload-token"


@pytest.mark.asyncio
async def test_user_avatar_attachment_replaces_only_a_valid_staged_avatar() -> None:
    storage = InMemoryObjectStorage()
    service, user, session = _service(storage)
    grant = await service.issue_upload(
        _principal(), "tenant_test", "user_test", "image/png", len(_image_bytes())
    )
    storage.objects[grant.object_key] = ObjectData(_image_bytes(), "image/png")

    assert await service.attach(_principal(), "tenant_test", "user_test", grant.object_key)

    session.commit.assert_awaited_once()
    assert grant.object_key in storage.deleted
    assert "avatars/users/user_test/previous.png" in storage.deleted
    assert user.avatar_key.startswith("avatars/users/user_test/avatar_")


@pytest.mark.asyncio
async def test_user_avatar_attachment_rejects_a_different_users_staged_object() -> None:
    storage = InMemoryObjectStorage()
    service, _, _ = _service(storage)

    with pytest.raises(AppError, match="does not belong"):
        await service.attach(
            _principal(),
            "tenant_test",
            "user_test",
            "staging/user-avatars/tenant_test/other_user/upload_x",
        )


@pytest.mark.asyncio
async def test_self_avatar_upload_is_bound_to_the_authenticated_subject() -> None:
    storage = InMemoryObjectStorage()
    service, _, _ = _service(storage)
    get_user = AsyncMock()
    mocked_service = cast(Any, service)
    mocked_service._enter_self_tenant = AsyncMock(return_value="tenant_test")
    mocked_service._get_tenant_user = get_user

    grant = await service.issue_self_upload(_principal(), "image/png", len(_image_bytes()))

    assert grant.object_key.startswith("staging/user-avatars/tenant_test/admin_test/upload_")
    get_user.assert_awaited_once_with("tenant_test", "admin_test")
