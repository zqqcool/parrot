from __future__ import annotations

import asyncio
import importlib
from collections.abc import Callable
from datetime import timedelta
from typing import Protocol, cast
from urllib.parse import quote

import httpx

from app.core.clock import utc_now
from app.core.config import ObjectStorageSection
from app.core.object_storage import (
    ObjectData,
    ObjectStorageDestinationConflictError,
    ObjectStorageOperationError,
    ObjectStoragePort,
    ObjectUploadGrant,
)

PRIVATE_DOWNLOAD_SECONDS = 60
QINIU_DETECTED_MIME_ALIASES = {
    "text/markdown": ("application/octet-stream",),
}


class QiniuResponse(Protocol):
    status_code: int


class QiniuAuth(Protocol):
    def upload_token(
        self,
        bucket: str,
        key: str,
        expires: int,
        policy: dict[str, int | str],
    ) -> str: ...

    def private_download_url(self, url: str, expires: int) -> str: ...


class QiniuBucketManager(Protocol):
    def delete(self, bucket: str, key: str) -> tuple[object | None, QiniuResponse]: ...

    def move(
        self,
        bucket: str,
        key: str,
        target_bucket: str,
        target_key: str,
        force: str = "false",
    ) -> tuple[object | None, QiniuResponse]: ...


QiniuAuthFactory = Callable[[str, str], QiniuAuth]
QiniuBucketManagerFactory = Callable[[QiniuAuth], QiniuBucketManager]


class QiniuPutData(Protocol):
    def __call__(
        self,
        upload_token: str,
        key: str,
        content: bytes,
        params: None = None,
        mime_type: str = "application/octet-stream",
    ) -> tuple[object | None, QiniuResponse]: ...


def _qiniu_sdk() -> tuple[QiniuAuthFactory, QiniuBucketManagerFactory, QiniuPutData]:
    module = importlib.import_module("qiniu")
    return (
        cast(QiniuAuthFactory, module.Auth),
        cast(QiniuBucketManagerFactory, module.BucketManager),
        cast(QiniuPutData, module.put_data),
    )


class QiniuObjectStorage(ObjectStoragePort):
    """Qiniu Kodo storage using official upload-token and resource-management SDKs."""

    def __init__(self, settings: ObjectStorageSection) -> None:
        self.settings = settings
        auth_factory, bucket_manager_factory, self._put_data = _qiniu_sdk()
        self._auth = auth_factory(settings.access_key, settings.secret_key)
        self._bucket_manager = bucket_manager_factory(self._auth)

    async def issue_upload_grant(
        self, key: str, content_type: str, size_bytes: int
    ) -> ObjectUploadGrant:
        upload_key = self._storage_key(key)
        upload_token = await asyncio.to_thread(
            self._upload_token, upload_key, content_type, size_bytes
        )
        return ObjectUploadGrant(
            object_key=key,
            upload_key=upload_key,
            upload_token=upload_token,
            expires_at=utc_now() + timedelta(seconds=self.settings.upload_token_seconds),
        )

    async def write(self, key: str, content: bytes, content_type: str) -> None:
        await asyncio.to_thread(self._write_data, self._storage_key(key), content, content_type)

    async def move(self, source_key: str, target_key: str) -> None:
        await asyncio.to_thread(
            self._move, self._storage_key(source_key), self._storage_key(target_key)
        )

    async def read(self, key: str) -> ObjectData | None:
        url = await asyncio.to_thread(self._private_download_url, self._storage_key(key))
        async with httpx.AsyncClient(timeout=PRIVATE_DOWNLOAD_SECONDS) as client:
            response = await client.get(url)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return ObjectData(
            content=response.content, content_type=response.headers.get("content-type")
        )

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._delete, self._storage_key(key))

    def _upload_token(self, key: str, content_type: str, size_bytes: int) -> str:
        return self._auth.upload_token(
            self.settings.bucket,
            key,
            self.settings.upload_token_seconds,
            {
                "insertOnly": 1,
                "fsizeLimit": size_bytes,
                "mimeLimit": _qiniu_mime_limit(content_type),
            },
        )

    def _write_data(self, key: str, content: bytes, content_type: str) -> None:
        upload_token = self._upload_token(key, content_type, len(content))
        result, info = self._put_data(upload_token, key, content, mime_type=content_type)
        self._ensure_success(result, info)

    def _private_download_url(self, key: str) -> str:
        base_url = f"{self.settings.download_domain.rstrip('/')}/{quote(key, safe='/')}"
        return self._auth.private_download_url(base_url, expires=PRIVATE_DOWNLOAD_SECONDS)

    def _storage_key(self, key: str) -> str:
        return f"{self.settings.key_prefix}/{key}"

    def _delete(self, key: str) -> None:
        _, info = self._bucket_manager.delete(self.settings.bucket, key)
        if getattr(info, "status_code", None) == 612:
            return
        self._ensure_management_success(info)

    def _move(self, source_key: str, target_key: str) -> None:
        _, info = self._bucket_manager.move(
            self.settings.bucket,
            source_key,
            self.settings.bucket,
            target_key,
            force="false",
        )
        if getattr(info, "status_code", None) == 614:
            raise ObjectStorageDestinationConflictError(status_code=614)
        self._ensure_management_success(info)

    @staticmethod
    def _ensure_success(result: object | None, info: QiniuResponse) -> None:
        if result is None or getattr(info, "status_code", None) not in {200, 204}:
            raise ObjectStorageOperationError("write", getattr(info, "status_code", None))

    @staticmethod
    def _ensure_management_success(info: QiniuResponse) -> None:
        if getattr(info, "status_code", None) not in {200, 204}:
            raise ObjectStorageOperationError("management", getattr(info, "status_code", None))


def _qiniu_mime_limit(content_type: str) -> str:
    aliases = QINIU_DETECTED_MIME_ALIASES.get(content_type, ())
    return ";".join((content_type, *aliases))
