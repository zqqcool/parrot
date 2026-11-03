from __future__ import annotations

import base64
from typing import TYPE_CHECKING
from urllib.parse import unquote, urlsplit

if TYPE_CHECKING:
    from app.core.config import AppConfig

_PLACEHOLDERS = ("test-only-", "overridden-by-", "replace-", "change-me")


def validate_production_secrets(config: AppConfig) -> None:
    encoded = config.security.credential_encryption_key.get_secret_value()
    values = [
        config.security.session_pepper,
        encoded,
        config.object_storage.access_key,
        config.object_storage.secret_key,
        *config.memory_credentials.values.values(),
        *config.knowledge_credentials.values.values(),
    ]
    for url in (
        config.database.url,
        config.database.platform_url,
        config.database.migration_url,
        config.redis.url,
    ):
        if password := urlsplit(url).password:
            values.append(unquote(password))
    if not encoded.startswith("overridden-by-"):
        decoded = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        values.append(decoded.decode("ascii", errors="replace"))
    if any(value.casefold().startswith(_PLACEHOLDERS) for value in values):
        raise ValueError("production requires deployment secrets, not public test placeholders")
