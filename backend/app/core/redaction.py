from __future__ import annotations

import re

REDACTED = "[REDACTED]"
_SENSITIVE_PARTS = (
    "authorization",
    "credential",
    "password",
    "passwd",
    "secret",
    "token",
    "apikey",
    "accesskey",
    "cookie",
    "sessionpepper",
)
_PRIVATE_KEY = re.compile(
    r"-----BEGIN ([A-Z ]*PRIVATE KEY)-----.*?(?:-----END \1-----|$)", re.DOTALL
)
_COOKIE_HEADER = re.compile(r"(?im)\b(?:set-cookie|cookie)\s*:\s*[^\r\n]+")
_AUTHORIZATION = re.compile(r"\b(Bearer|Basic)\s+[^\s\"',;<>]+", re.IGNORECASE)
_ASSIGNMENT = re.compile(
    r"(?i)\b(?:api[_ -]?key|access[_ -]?(?:token|key)(?:[_ -]?id)?|"
    r"secret(?:[_ -]?(?:access[_ -]?)?key)?|password|passwd|"
    r"session[_ -]?pepper|credential(?:[_ -]?encryption[_ -]?key)?|"
    r"authorization|cookie|set-cookie|csrf[_ -]?token)"
    r"[\"']?\s*[:=]\s*(?:\"[^\"]*\"|'[^']*'|[^\s,;&<>]+)"
)
_TOKEN = re.compile(
    r"\b(?:sk|ark)-[a-zA-Z0-9_-]{8,}\b|\bgh[pousr]_[a-zA-Z0-9]{20,}|"
    r"\bgithub_pat_[a-zA-Z0-9_]{30,}|\bglpat-[a-zA-Z0-9_-]{16,}|\bAKIA[A-Z0-9]{16}"
)
_URL = re.compile(r"\b[a-zA-Z][a-zA-Z0-9+.-]*://[^\s\"'<>]+")
_USERINFO = re.compile(r"(://)[^/@\s]+@")


def is_sensitive_key(key: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", key.casefold())
    return any(part in normalized for part in _SENSITIVE_PARTS)


def redact_sensitive_text(value: str, *, hide_urls: bool = False) -> str:
    """Apply credential-pattern defense in depth; callers must still exclude private content."""
    value = _PRIVATE_KEY.sub(REDACTED, value)
    value = _COOKIE_HEADER.sub(REDACTED, value)
    if hide_urls:
        value = _URL.sub(REDACTED, value)
    else:
        value = _USERINFO.sub(r"\1[REDACTED]@", value)
    value = _AUTHORIZATION.sub(r"\1 [REDACTED]", value)
    value = _ASSIGNMENT.sub(REDACTED, value)
    return _TOKEN.sub(REDACTED, value)
