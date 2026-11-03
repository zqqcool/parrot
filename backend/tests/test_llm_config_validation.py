from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
from _agent_runtime_support import credential_cipher
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import load_app_config
from app.core.errors import AppError
from app.infrastructure.db.session import DatabaseManager
from app.modules.iam.schemas import PrincipalContext
from app.modules.llm_configs.models import LlmConfig
from app.modules.llm_configs.schemas import LlmConfigCreateRequest, LlmConfigUpdateRequest
from app.modules.llm_configs.service import LlmConfigService


def test_llm_config_creation_requires_endpoint() -> None:
    with pytest.raises(ValidationError, match="base_url"):
        LlmConfigCreateRequest.model_validate(
            {
                "name": "Primary",
                "provider": "openai",
                "model": "gpt-4.1",
                "api_key": "test-key",
            }
        )


def test_llm_config_update_cannot_clear_endpoint() -> None:
    with pytest.raises(ValidationError, match="base_url cannot be null"):
        LlmConfigUpdateRequest(base_url=None)


def test_llm_config_thinking_mode_is_explicit_and_disabled_by_default() -> None:
    created = LlmConfigCreateRequest.model_validate(
        {
            "name": "Primary",
            "provider": "openai-compatible",
            "model": "model-test",
            "base_url": "https://model.example.test/v1",
            "api_key": "test-key",
        }
    )
    updated = LlmConfigUpdateRequest(thinking_enabled=True)

    assert created.thinking_enabled is False
    assert updated.thinking_enabled is True


def test_llm_config_prompt_cache_is_explicit_and_disabled_by_default() -> None:
    created = LlmConfigCreateRequest.model_validate(
        {
            "name": "Primary",
            "provider": "openai-compatible",
            "model": "model-test",
            "base_url": "https://model.example.test/v1",
            "api_key": "test-key",
        }
    )
    updated = LlmConfigUpdateRequest(prompt_cache_enabled=True)

    assert created.prompt_cache_enabled is False
    assert updated.prompt_cache_enabled is True


@pytest.mark.asyncio
async def test_llm_config_update_requires_endpoint_for_legacy_configuration() -> None:
    model = LlmConfig(
        id="llm_test",
        tenant_id="tenant_test",
        name="Primary",
        provider="openai",
        model="gpt-4.1",
        base_url=None,
        credential_envelope=None,
        temperature=0.2,
        max_tokens=4096,
        thinking_enabled=False,
        prompt_cache_enabled=False,
        status="active",
        is_default=True,
    )
    session = cast(AsyncSession, SimpleNamespace(scalar=AsyncMock(return_value=model)))
    database = cast(DatabaseManager, SimpleNamespace(set_tenant=AsyncMock()))
    service = LlmConfigService(session, database, credential_cipher(), load_app_config())
    principal = PrincipalContext(
        tenant_id="tenant_test",
        subject_id="user_test",
        username="admin",
        display_name="Admin",
        permissions=("llm_configs.manage",),
        tenants=(),
        must_change_password=False,
        request_id="req_test",
    )

    with pytest.raises(AppError, match="Model endpoint must be configured") as error:
        await service.update(
            principal,
            "tenant_test",
            "llm_test",
            LlmConfigUpdateRequest(name="Renamed"),
        )

    assert error.value.code == "LLM_CONFIG_ENDPOINT_REQUIRED"
    assert error.value.status_code == 422


@pytest.mark.asyncio
async def test_llm_provider_change_requires_a_new_credential() -> None:
    model = LlmConfig(
        id="llm_test",
        tenant_id="tenant_test",
        name="Primary",
        provider="openai",
        model="gpt-4.1",
        base_url="https://api.openai.com/v1",
        credential_envelope="v1.encrypted",
        temperature=0.2,
        max_tokens=4096,
        thinking_enabled=False,
        prompt_cache_enabled=False,
        status="active",
        is_default=True,
    )
    session = cast(AsyncSession, SimpleNamespace(scalar=AsyncMock(return_value=model)))
    database = cast(DatabaseManager, SimpleNamespace(set_tenant=AsyncMock()))
    service = LlmConfigService(session, database, credential_cipher(), load_app_config())
    principal = PrincipalContext(
        tenant_id="tenant_test",
        subject_id="user_test",
        username="admin",
        display_name="Admin",
        permissions=("llm_configs.manage",),
        tenants=(),
        must_change_password=False,
        request_id="req_test",
    )

    with pytest.raises(AppError) as error:
        await service.update(
            principal,
            "tenant_test",
            "llm_test",
            LlmConfigUpdateRequest(
                provider="volcengine_ark",
                base_url="https://ark.cn-beijing.volces.com/api/v3",
            ),
        )

    assert error.value.code == "MODEL_PROVIDER_CREDENTIAL_REQUIRED"
