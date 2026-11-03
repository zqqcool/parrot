from __future__ import annotations

import hashlib
import hmac

from app.core.object_storage import ObjectStorageOperationError, ObjectStoragePort

_OBJECT_EXISTS_STATUS = 614


async def write_media_object(
    storage: ObjectStoragePort,
    key: str,
    content: bytes,
    content_type: str,
) -> None:
    try:
        await storage.write(key, content, content_type)
    except ObjectStorageOperationError as exc:
        if exc.status_code != _OBJECT_EXISTS_STATUS:
            raise
        existing = await storage.read(key)
        if existing is None or not hmac.compare_digest(
            hashlib.sha256(existing.content).digest(),
            hashlib.sha256(content).digest(),
        ):
            raise
