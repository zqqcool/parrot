from datetime import UTC, datetime

import pytest

from app.core.config import ObjectStorageSection
from app.core.object_storage import ObjectStorageDestinationConflictError
from app.infrastructure.qiniu_object_storage import (
    QiniuObjectStorage,
    _qiniu_mime_limit,  # pyright: ignore[reportPrivateUsage]
)


class StubQiniuObjectStorage(QiniuObjectStorage):
    def __init__(self, settings: ObjectStorageSection) -> None:
        super().__init__(settings)
        self.upload_requests: list[tuple[str, str, int]] = []
        self.move_requests: list[tuple[str, str]] = []

    def _upload_token(self, key: str, content_type: str, size_bytes: int) -> str:
        self.upload_requests.append((key, content_type, size_bytes))
        return "qiniu-upload-token"

    def _move(self, source_key: str, target_key: str) -> None:
        self.move_requests.append((source_key, target_key))


class StubQiniuResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class ExistingDestinationBucketManager:
    def __init__(self) -> None:
        self.move_requests: list[tuple[str, str, str, str, str]] = []

    def delete(self, bucket: str, key: str) -> tuple[object | None, StubQiniuResponse]:
        del bucket, key
        return None, StubQiniuResponse(612)

    def move(
        self,
        bucket: str,
        key: str,
        target_bucket: str,
        target_key: str,
        force: str = "false",
    ) -> tuple[object | None, StubQiniuResponse]:
        self.move_requests.append((bucket, key, target_bucket, target_key, force))
        return None, StubQiniuResponse(614)


def _settings() -> ObjectStorageSection:
    return ObjectStorageSection(
        bucket="parrot-test-bucket",
        key_prefix="parrot",
        download_domain="https://storage.example.invalid",
        access_key="access-key",
        secret_key="secret-key",
    )


@pytest.mark.asyncio
async def test_qiniu_upload_token_is_limited_to_the_requested_object_and_size() -> None:
    storage = StubQiniuObjectStorage(_settings())

    grant = await storage.issue_upload_grant("staging/tenant_test/upload_test", "image/png", 1_024)

    assert grant.object_key == "staging/tenant_test/upload_test"
    assert grant.upload_key == "parrot/staging/tenant_test/upload_test"
    assert grant.upload_token == "qiniu-upload-token"
    assert grant.expires_at > datetime.now(UTC)
    assert storage.upload_requests == [
        ("parrot/staging/tenant_test/upload_test", "image/png", 1_024)
    ]


@pytest.mark.asyncio
async def test_qiniu_move_promotes_a_staged_object_without_reuploading() -> None:
    storage = StubQiniuObjectStorage(_settings())

    await storage.move("staging/tenant_test/upload_test", "knowledge/tenant_test/source_test")

    assert storage.move_requests == [
        ("parrot/staging/tenant_test/upload_test", "parrot/knowledge/tenant_test/source_test")
    ]


def test_qiniu_move_classifies_an_existing_destination() -> None:
    storage = QiniuObjectStorage(_settings())
    manager = ExistingDestinationBucketManager()
    storage._bucket_manager = manager  # pyright: ignore[reportPrivateUsage]

    with pytest.raises(ObjectStorageDestinationConflictError):
        storage._move("parrot/staging/source", "parrot/knowledge/source")  # pyright: ignore[reportPrivateUsage]

    assert manager.move_requests == [
        (
            "parrot-test-bucket",
            "parrot/staging/source",
            "parrot-test-bucket",
            "parrot/knowledge/source",
            "false",
        )
    ]


def test_qiniu_markdown_mime_limit_allows_provider_detection_fallback() -> None:
    assert _qiniu_mime_limit("text/markdown") == "text/markdown;application/octet-stream"
    assert _qiniu_mime_limit("application/pdf") == "application/pdf"
