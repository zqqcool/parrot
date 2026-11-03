from __future__ import annotations

import hashlib
import logging

from starlette import status

from app.core.errors import AppError
from app.core.object_storage import (
    ObjectData,
    ObjectStorageDestinationConflictError,
    ObjectStorageOperationError,
    ObjectStoragePort,
)

logger = logging.getLogger(__name__)

_MISSING_OBJECT_STATUS_CODES = frozenset({404, 612})


class KnowledgeStagingObjectGoneError(Exception):
    """Staging object is missing from durable object storage and cannot be promoted."""

    def __init__(self, *, status_code: int | None = None) -> None:
        super().__init__("Knowledge staging object is gone")
        self.status_code = status_code


async def promote_staged_object(
    storage: ObjectStoragePort,
    staging_key: str,
    canonical_key: str,
    staged: ObjectData,
) -> None:
    try:
        await storage.move(staging_key, canonical_key)
    except ObjectStorageDestinationConflictError:
        await _recover_matching_canonical(storage, staging_key, canonical_key, staged)
    except ObjectStorageOperationError as exc:
        if exc.status_code in _MISSING_OBJECT_STATUS_CODES:
            logger.warning(
                "Knowledge staging object missing during promotion",
                extra={"operation": exc.operation, "status_code": exc.status_code},
            )
            raise KnowledgeStagingObjectGoneError(status_code=exc.status_code) from exc
        _raise_source_unavailable(exc)


async def _recover_matching_canonical(
    storage: ObjectStoragePort,
    staging_key: str,
    canonical_key: str,
    staged: ObjectData,
) -> None:
    try:
        canonical = await storage.read(canonical_key)
        if (
            canonical is None
            or hashlib.sha256(canonical.content).digest() != hashlib.sha256(staged.content).digest()
        ):
            raise AppError(
                "KNOWLEDGE_SOURCE_STATE_INVALID",
                "Knowledge source canonical object conflicts with the staging object",
                status.HTTP_409_CONFLICT,
            )
        await storage.delete(staging_key)
    except ObjectStorageOperationError as exc:
        _raise_source_unavailable(exc)


def _raise_source_unavailable(exc: ObjectStorageOperationError) -> None:
    logger.warning(
        "Knowledge object storage promotion failed",
        extra={"operation": exc.operation, "status_code": exc.status_code},
    )
    raise AppError(
        "KNOWLEDGE_SOURCE_UNAVAILABLE",
        "Knowledge object storage is unavailable",
        status.HTTP_503_SERVICE_UNAVAILABLE,
    ) from exc
