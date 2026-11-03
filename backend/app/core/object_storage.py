from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


class ObjectStorageOperationError(RuntimeError):
    """A bounded failure returned by an object-storage provider."""

    def __init__(self, operation: str, status_code: int | None = None) -> None:
        super().__init__(f"Object storage {operation} failed")
        self.operation = operation
        self.status_code = status_code


class ObjectStorageDestinationConflictError(ObjectStorageOperationError):
    """The server-owned destination key already exists."""

    def __init__(self, status_code: int | None = None) -> None:
        super().__init__("move", status_code)


@dataclass(frozen=True)
class ObjectData:
    content: bytes
    content_type: str | None


@dataclass(frozen=True)
class ObjectUploadGrant:
    """A narrowly scoped, short-lived Qiniu browser upload capability."""

    object_key: str
    upload_key: str
    upload_token: str
    expires_at: datetime


class ObjectStoragePort(Protocol):
    async def issue_upload_grant(
        self, key: str, content_type: str, size_bytes: int
    ) -> ObjectUploadGrant: ...

    async def write(self, key: str, content: bytes, content_type: str) -> None: ...

    async def move(self, source_key: str, target_key: str) -> None: ...

    async def read(self, key: str) -> ObjectData | None: ...

    async def delete(self, key: str) -> None: ...
