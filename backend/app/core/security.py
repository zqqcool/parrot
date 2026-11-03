from __future__ import annotations

import hashlib
import hmac
import secrets

from pwdlib import PasswordHash

password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, encoded_hash: str) -> bool:
    return password_hash.verify(password, encoded_hash)


def new_secret(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(32)}"


def secret_digest(secret: str, pepper: str, purpose: str) -> str:
    message = f"{purpose}:{secret}".encode()
    return hmac.new(pepper.encode(), message, hashlib.sha256).hexdigest()


def csrf_token(session_token: str, pepper: str) -> str:
    return secret_digest(session_token, pepper, "csrf")


def constant_time_equal(left: str, right: str) -> bool:
    return hmac.compare_digest(left, right)
