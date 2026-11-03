import base64
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import load_app_config
from app.core.errors import AppError
from app.infrastructure.credential_cipher import (
    CredentialCipher,
    CredentialCipherError,
    llm_credential_context,
    mcp_credential_context,
)
from app.infrastructure.db.session import DatabaseManager
from app.modules.iam.schemas import PrincipalContext
from app.modules.llm_configs.models import LlmConfig
from app.modules.llm_configs.schemas import LlmConfigCreateRequest
from app.modules.llm_configs.service import LlmConfigService
from app.modules.mcp_servers.models import McpServer
from app.modules.mcp_servers.schemas import McpServerCreateRequest
from app.modules.mcp_servers.service import McpServerService


def _key(value: bytes = b"0" * 32) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _principal(*permissions: str) -> PrincipalContext:
    return PrincipalContext(
        tenant_id="tenant_test",
        subject_id="user_test",
        username="admin",
        display_name="Admin",
        permissions=permissions,
        tenants=(),
        must_change_password=False,
        request_id="request_test",
    )


def test_credential_cipher_uses_random_authenticated_envelopes() -> None:
    cipher = CredentialCipher(_key())
    context = llm_credential_context("llm_test")

    first = cipher.encrypt("provider-secret", context=context)
    second = cipher.encrypt("provider-secret", context=context)

    assert first.startswith("v1.")
    assert first != second
    assert "provider-secret" not in first
    assert cipher.decrypt(first, context=context) == "provider-secret"


def test_credential_cipher_rejects_wrong_record_context_key_and_tampering() -> None:
    cipher = CredentialCipher(_key())
    envelope = cipher.encrypt(
        "provider-secret", context=mcp_credential_context("mcp_one", "header", "Authorization")
    )

    with pytest.raises(CredentialCipherError):
        cipher.decrypt(
            envelope, context=mcp_credential_context("mcp_two", "header", "Authorization")
        )
    with pytest.raises(CredentialCipherError):
        CredentialCipher(_key(b"1" * 32)).decrypt(
            envelope, context=mcp_credential_context("mcp_one", "header", "Authorization")
        )
    version, payload = envelope.split(".", 1)
    raw = bytearray(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    raw[-1] ^= 1
    tampered = f"{version}.{base64.urlsafe_b64encode(raw).decode().rstrip('=')}"
    with pytest.raises(CredentialCipherError):
        cipher.decrypt(
            tampered,
            context=mcp_credential_context("mcp_one", "header", "Authorization"),
        )


def test_management_views_never_expose_encrypted_values() -> None:
    llm = LlmConfig(
        id="llm_test",
        tenant_id="tenant_test",
        name="Primary",
        provider="openai-compatible",
        model="model-test",
        base_url="https://models.example.test/v1",
        credential_envelope="v1.sensitive-ciphertext",
        temperature=0.2,
        max_tokens=4096,
        thinking_enabled=False,
        prompt_cache_enabled=False,
        status="active",
        is_default=True,
    )
    mcp = McpServer(
        id="mcp_test",
        tenant_id="tenant_test",
        name="docs",
        transport="streamable_http",
        endpoint="https://mcp.example.test",
        arguments=[],
        encrypted_credentials=[
            {"target": "header", "name": "Authorization", "envelope": "v1.secret"}
        ],
        status="active",
    )

    llm_payload = LlmConfigService.view(llm).model_dump()
    mcp_payload = McpServerService.view(mcp).model_dump()

    assert llm_payload["credential_configured"] is True
    assert "credential_envelope" not in llm_payload
    assert mcp_payload["credentials"] == [
        {"target": "header", "name": "Authorization", "configured": True}
    ]
    assert "encrypted_credentials" not in mcp_payload


@pytest.mark.asyncio
async def test_llm_creation_encrypts_api_key_before_database_add() -> None:
    cipher = CredentialCipher(_key())
    add = Mock()

    async def flush() -> None:
        cast(LlmConfig, add.call_args_list[0].args[0]).status = "active"

    session = cast(AsyncSession, SimpleNamespace(add=add, flush=AsyncMock(side_effect=flush)))
    database = cast(DatabaseManager, SimpleNamespace(set_tenant=AsyncMock()))
    service = LlmConfigService(session, database, cipher, load_app_config())

    view = await service.create(
        _principal("llm_configs.manage"),
        "tenant_test",
        LlmConfigCreateRequest.model_validate(
            {
                "name": "Primary",
                "provider": "openai",
                "model": "model-test",
                "base_url": "https://models.example.test/v1",
                "api_key": "provider-secret",
            }
        ),
    )

    stored = cast(LlmConfig, add.call_args_list[0].args[0])
    assert stored.credential_envelope != "provider-secret"
    assert (
        cipher.decrypt(
            cast(str, stored.credential_envelope), context=llm_credential_context(stored.id)
        )
        == "provider-secret"
    )
    assert view.credential_configured is True
    assert add.call_args_list[1].args[0].metadata_json == {}


@pytest.mark.asyncio
async def test_mcp_creation_encrypts_each_account_value_before_database_add() -> None:
    cipher = CredentialCipher(_key())
    add = Mock()

    async def flush() -> None:
        cast(McpServer, add.call_args_list[0].args[0]).status = "active"

    session = cast(
        AsyncSession,
        SimpleNamespace(
            add=add, flush=AsyncMock(side_effect=flush), scalars=AsyncMock(return_value=[])
        ),
    )
    database = cast(DatabaseManager, SimpleNamespace(set_tenant=AsyncMock()))
    service = McpServerService(session, database, cipher)

    view = await service.create(
        _principal("mcp_servers.manage"),
        "tenant_test",
        McpServerCreateRequest.model_validate(
            {
                "name": "Docs",
                "transport": "streamable_http",
                "endpoint": "https://mcp.example.test",
                "credentials": [
                    {
                        "target": "header",
                        "name": "Authorization",
                        "secret": "Bearer secret",
                    }
                ],
            }
        ),
    )

    stored = cast(McpServer, add.call_args_list[0].args[0])
    encrypted = stored.encrypted_credentials[0]
    assert encrypted["envelope"] != "Bearer secret"
    assert (
        cipher.decrypt(
            encrypted["envelope"],
            context=mcp_credential_context(stored.id, "header", "Authorization"),
        )
        == "Bearer secret"
    )
    assert view.credentials[0].configured is True
    assert add.call_args_list[1].args[0].metadata_json == {}


@pytest.mark.asyncio
async def test_mcp_creation_rejects_credential_target_incompatible_with_transport() -> None:
    cipher = CredentialCipher(_key())
    add = Mock()
    session = cast(AsyncSession, SimpleNamespace(add=add, flush=AsyncMock()))
    database = cast(DatabaseManager, SimpleNamespace(set_tenant=AsyncMock()))
    service = McpServerService(session, database, cipher)

    with pytest.raises(
        AppError, match="streamable_http MCP credentials must use header targets"
    ) as error:
        await service.create(
            _principal("mcp_servers.manage"),
            "tenant_test",
            McpServerCreateRequest.model_validate(
                {
                    "name": "Docs",
                    "transport": "streamable_http",
                    "endpoint": "https://mcp.example.test",
                    "credentials": [{"target": "env", "name": "API_KEY", "secret": "secret"}],
                }
            ),
        )

    assert error.value.code == "MCP_CREDENTIAL_TARGET_INVALID"
    add.assert_not_called()
