from __future__ import annotations

import base64
import binascii
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_ENVELOPE_VERSION = "v1"
_NONCE_BYTES = 12


class CredentialCipherError(RuntimeError):
    pass


class CredentialCipher:
    """Versioned AEAD encryption for database-backed provider credentials."""

    def __init__(self, encoded_key: str) -> None:
        try:
            padded = encoded_key + "=" * (-len(encoded_key) % 4)
            key = base64.urlsafe_b64decode(padded.encode())
        except (ValueError, binascii.Error) as error:
            raise ValueError("credential encryption key must use URL-safe base64") from error
        if len(key) != 32:
            raise ValueError("credential encryption key must decode to exactly 32 bytes")
        self._cipher = AESGCM(key)

    def encrypt(self, plaintext: str, *, context: str) -> str:
        if not plaintext:
            raise ValueError("credential must not be empty")
        nonce = os.urandom(_NONCE_BYTES)
        ciphertext = self._cipher.encrypt(nonce, plaintext.encode(), context.encode())
        payload = base64.urlsafe_b64encode(nonce + ciphertext).decode().rstrip("=")
        return f"{_ENVELOPE_VERSION}.{payload}"

    def decrypt(self, envelope: str, *, context: str) -> str:
        try:
            version, payload = envelope.split(".", 1)
            if version != _ENVELOPE_VERSION:
                raise CredentialCipherError("credential envelope version is unsupported")
            padded = payload + "=" * (-len(payload) % 4)
            raw = base64.urlsafe_b64decode(padded.encode())
            if len(raw) <= _NONCE_BYTES:
                raise CredentialCipherError("credential envelope is invalid")
            plaintext = self._cipher.decrypt(
                raw[:_NONCE_BYTES], raw[_NONCE_BYTES:], context.encode()
            )
            return plaintext.decode()
        except CredentialCipherError:
            raise
        except (ValueError, UnicodeDecodeError, InvalidTag, binascii.Error) as error:
            raise CredentialCipherError("credential envelope cannot be decrypted") from error


def llm_credential_context(config_id: str) -> str:
    return f"llm-config:{config_id}:api-key"


def embedding_credential_context(config_id: str) -> str:
    """Bind an embedding key to exactly one tenant-owned configuration record."""
    return f"embedding-config:{config_id}:api-key"


def reranker_credential_context(config_id: str) -> str:
    """Bind a reranker key to exactly one tenant-owned configuration record."""
    return f"reranker-config:{config_id}:api-key"


def mcp_credential_context(server_id: str, target: str, name: str) -> str:
    return f"mcp-server:{server_id}:{target}:{name}"
