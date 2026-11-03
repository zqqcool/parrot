from datetime import UTC, datetime, timedelta
from io import BytesIO
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.object_storage import ObjectData, ObjectStoragePort, ObjectUploadGrant
from app.infrastructure.db.session import DatabaseManager
from app.modules.agents.avatar_validation import validate_agent_avatar
from app.modules.agents.service import AgentService
from app.modules.iam.schemas import PrincipalContext


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


def _image_bytes(image_format: str = "PNG") -> bytes:
    output = BytesIO()
    Image.new("RGB", (1, 1), "white").save(output, format=image_format)
    return output.getvalue()


def _principal() -> PrincipalContext:
    return PrincipalContext(
        tenant_id="tenant_test",
        subject_id="user_test",
        username="admin",
        display_name="Admin",
        permissions=("agents.manage",),
        tenants=(),
        must_change_password=False,
        request_id="req_test",
    )


def _service(
    storage: InMemoryObjectStorage,
) -> tuple[AgentService, SimpleNamespace, SimpleNamespace]:
    model = SimpleNamespace(
        id="agent_test",
        tenant_id="tenant_test",
        runtime_agent_id="runtime_test",
        slug="demo-agent",
        name="Demo agent",
        description="",
        system_prompt="",
        status="active",
        agent_type_key="general",
        published=False,
        allow_anonymous=False,
        avatar_key="avatars/previous.png",
        avatar_content_type="image/png",
    )
    result = SimpleNamespace(scalar_one_or_none=Mock(return_value=model))
    session = SimpleNamespace(
        execute=AsyncMock(return_value=result),
        flush=AsyncMock(),
        commit=AsyncMock(),
        rollback=AsyncMock(),
        add=Mock(),
    )
    database = SimpleNamespace(set_tenant=AsyncMock())
    return (
        AgentService(
            cast(AsyncSession, session),
            cast(DatabaseManager, database),
            object_storage=cast(ObjectStoragePort, storage),
        ),
        model,
        session,
    )


def test_avatar_validation_uses_decoded_content_type() -> None:
    avatar = validate_agent_avatar(_image_bytes(), "image/png", 2 * 1024 * 1024)

    assert avatar.content_type == "image/png"
    assert avatar.extension == "png"


def test_avatar_validation_rejects_mismatched_content_type() -> None:
    with pytest.raises(AppError) as error:
        validate_agent_avatar(_image_bytes(), "image/jpeg", 2 * 1024 * 1024)

    assert error.value.code == "AVATAR_TYPE_INVALID"


@pytest.mark.asyncio
async def test_avatar_upload_grant_is_scoped_to_the_authorized_agent() -> None:
    storage = InMemoryObjectStorage()
    service, _, _ = _service(storage)

    grant = await service.issue_avatar_upload(
        _principal(), "tenant_test", "agent_test", "image/png", 5
    )

    assert grant.object_key.startswith("staging/agent-avatars/tenant_test/agent_test/upload_")
    assert grant.upload_token == "upload-token"


@pytest.mark.asyncio
async def test_avatar_attachment_validates_staged_object_before_replacing_previous_object() -> None:
    storage = InMemoryObjectStorage()
    service, model, session = _service(storage)
    grant = await service.issue_avatar_upload(
        _principal(), "tenant_test", "agent_test", "image/png", len(_image_bytes())
    )
    storage.objects[grant.object_key] = ObjectData(_image_bytes(), "image/png")

    view = await service.attach_avatar(_principal(), "tenant_test", "agent_test", grant.object_key)

    session.commit.assert_awaited_once()
    assert grant.object_key in storage.deleted
    assert "avatars/previous.png" in storage.deleted
    assert model.avatar_key.startswith("avatars/tenant_test/agent_test/avatar_")
    assert view.avatar_present is True


@pytest.mark.asyncio
async def test_avatar_attachment_rejects_another_agents_staged_object() -> None:
    storage = InMemoryObjectStorage()
    service, _, _ = _service(storage)

    with pytest.raises(AppError, match="does not belong"):
        await service.attach_avatar(
            _principal(),
            "tenant_test",
            "agent_test",
            "staging/agent-avatars/tenant_test/other_agent/upload_x",
        )
