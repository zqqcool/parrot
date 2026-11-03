import pytest
from pwdlib.exceptions import UnknownHashError

from app.core.security import (
    constant_time_equal,
    csrf_token,
    hash_password,
    secret_digest,
    verify_password,
)


def test_password_hash_uses_argon2_and_verifies() -> None:
    encoded = hash_password("correct-horse-battery-staple")

    assert encoded.startswith("$argon2")
    assert verify_password("correct-horse-battery-staple", encoded)
    assert not verify_password("wrong-password", encoded)


def test_secret_digests_are_purpose_bound() -> None:
    session = secret_digest("token", "pepper", "session")
    visitor = secret_digest("token", "pepper", "visitor")

    assert session != visitor
    assert constant_time_equal(session, session)
    assert not constant_time_equal(session, visitor)
    assert csrf_token("token", "pepper") == secret_digest("token", "pepper", "csrf")


def test_password_verification_rejects_invalid_hash() -> None:
    with pytest.raises(UnknownHashError):
        verify_password("password", "not-a-password-hash")
