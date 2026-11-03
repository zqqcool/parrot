from __future__ import annotations

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.agent_runtime import RuntimeLlmProfile
from app.core.config import AppConfig
from app.core.errors import AppError
from app.core.ids import new_id
from app.infrastructure.credential_cipher import CredentialCipher, llm_credential_context
from app.infrastructure.db.session import DatabaseManager
from app.modules.agent_runtime.contracts import ChatMessage, ModelProviderError
from app.modules.audit.service import append_audit
from app.modules.iam.permissions import PLATFORM_TENANTS_MANAGE
from app.modules.iam.schemas import PrincipalContext
from app.modules.llm_configs.models import LlmConfig
from app.modules.llm_configs.schemas import (
    LlmConfigConnectionTestRequest,
    LlmConfigCreateRequest,
    LlmConfigUpdateRequest,
    LlmConfigView,
)
from app.modules.model_configs.connection_test import (
    CONNECTION_TEST_TIMEOUT_SECONDS,
    connection_test_failed,
)
from app.modules.model_configs.endpoint_policy import validate_model_endpoint
from app.modules.model_configs.schemas import ModelConnectionTestView
from app.modules.model_providers.catalog import (
    canonical_provider,
    provider_capability,
    selectable_provider_capability,
)
from app.modules.model_providers.llm import ProviderLlmClient


class LlmConfigService:
    def __init__(
        self,
        session: AsyncSession,
        database: DatabaseManager,
        cipher: CredentialCipher,
        settings: AppConfig,
    ) -> None:
        self.session = session
        self.database = database
        self.cipher = cipher
        self.settings = settings

    async def list(
        self, principal: PrincipalContext, tenant_id: str, *, query: str | None = None
    ) -> list[LlmConfigView]:
        await self._enter(principal, tenant_id, "llm_configs.read")
        statement = select(LlmConfig).where(LlmConfig.tenant_id == tenant_id)
        normalized = query.strip() if query else ""
        if normalized:
            statement = statement.where(
                or_(
                    LlmConfig.name.icontains(normalized, autoescape=True),
                    LlmConfig.provider.icontains(normalized, autoescape=True),
                    LlmConfig.model.icontains(normalized, autoescape=True),
                )
            )
        rows = await self.session.scalars(statement.order_by(LlmConfig.name))
        return [self.view(row) for row in rows]

    async def validate_ids(self, tenant_id: str, ids: tuple[str, ...]) -> None:
        if not ids:
            return
        found = await self.session.scalars(
            select(LlmConfig.id).where(
                LlmConfig.tenant_id == tenant_id,
                LlmConfig.id.in_(ids),
                LlmConfig.status == "active",
            )
        )
        if set(found) != set(ids):
            raise AppError(
                "LLM_CONFIG_NOT_FOUND",
                "One or more LLM configurations are unavailable",
                status.HTTP_404_NOT_FOUND,
            )

    async def create(
        self, principal: PrincipalContext, tenant_id: str, payload: LlmConfigCreateRequest
    ) -> LlmConfigView:
        await self._enter(principal, tenant_id, "llm_configs.manage")
        config_id = new_id("llm")
        values = payload.model_dump(exclude={"api_key"})
        values["provider"] = canonical_provider(payload.provider)
        selectable_provider_capability(str(values["provider"]), "llm")
        values["base_url"] = self._endpoint(str(values["provider"]), payload.base_url)
        model = LlmConfig(
            id=config_id,
            tenant_id=tenant_id,
            credential_envelope=self.cipher.encrypt(
                payload.api_key.get_secret_value(), context=llm_credential_context(config_id)
            ),
            **values,
        )
        if payload.is_default:
            await self._clear_default(tenant_id)
        self.session.add(model)
        await self.session.flush()
        append_audit(
            self.session,
            principal,
            "llm_config.create",
            "llm_config",
            model.id,
            tenant_id=tenant_id,
        )
        return self.view(model)

    async def update(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        config_id: str,
        payload: LlmConfigUpdateRequest,
    ) -> LlmConfigView:
        await self._enter(principal, tenant_id, "llm_configs.manage")
        model = await self._get(tenant_id, config_id)
        values = payload.model_dump(exclude_unset=True, exclude={"api_key"})
        provider = canonical_provider(str(values.get("provider", model.provider)))
        if "provider" in values:
            current_provider = canonical_provider(model.provider)
            if provider != current_provider:
                selectable_provider_capability(provider, "llm")
            values["provider"] = provider if provider != current_provider else model.provider
            if provider != current_provider and payload.api_key is None:
                raise AppError(
                    "MODEL_PROVIDER_CREDENTIAL_REQUIRED",
                    "Changing provider requires a new credential",
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                )
        if not _has_configured_endpoint(values.get("base_url", model.base_url)):
            raise AppError(
                "LLM_CONFIG_ENDPOINT_REQUIRED",
                "Model endpoint must be configured",
                status.HTTP_422_UNPROCESSABLE_CONTENT,
            )
        endpoint = self._endpoint(provider, str(values.get("base_url", model.base_url)))
        if "provider" in values or "base_url" in values:
            values["base_url"] = endpoint
        credential_changed = payload.api_key is not None
        if payload.api_key is not None:
            values["credential_envelope"] = self.cipher.encrypt(
                payload.api_key.get_secret_value(), context=llm_credential_context(config_id)
            )
        if values.get("is_default") is True:
            await self._clear_default(tenant_id)
        if values:
            await self.session.execute(
                update(LlmConfig).where(LlmConfig.id == config_id).values(**values)
            )
            await self.session.refresh(model)
        append_audit(
            self.session,
            principal,
            "llm_config.update",
            "llm_config",
            model.id,
            _audit_values(values, credential_changed=credential_changed),
            tenant_id=tenant_id,
        )
        return self.view(model)

    async def test_connection(
        self, principal: PrincipalContext, tenant_id: str, config_id: str
    ) -> ModelConnectionTestView:
        await self._enter(principal, tenant_id, "llm_configs.manage")
        model = await self._get(tenant_id, config_id)
        profile = RuntimeLlmProfile(
            id=model.id,
            provider=model.provider,
            model=model.model,
            base_url=model.base_url,
            credential_envelope=model.credential_envelope,
            temperature=model.temperature,
            max_tokens=model.max_tokens,
            thinking_enabled=model.thinking_enabled,
            prompt_cache_enabled=bool(model.prompt_cache_enabled),
        )
        try:
            await ProviderLlmClient(
                self.settings,
                self.cipher,
                timeout_seconds=CONNECTION_TEST_TIMEOUT_SECONDS,
            ).complete(
                profile,
                (ChatMessage(role="user", content="Reply with OK."),),
            )
        except ModelProviderError as error:
            raise connection_test_failed(error) from error
        return ModelConnectionTestView(connected=True)

    async def test_draft_connection(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        payload: LlmConfigConnectionTestRequest,
    ) -> ModelConnectionTestView:
        await self._enter(principal, tenant_id, "llm_configs.manage")
        saved = await self._get(tenant_id, payload.config_id) if payload.config_id else None
        provider = canonical_provider(payload.provider)
        if (
            saved is not None
            and canonical_provider(saved.provider) != provider
            and payload.api_key is None
        ):
            raise AppError(
                "MODEL_PROVIDER_CREDENTIAL_REQUIRED",
                "Changing provider requires a new credential",
                status.HTTP_422_UNPROCESSABLE_CONTENT,
            )
        if saved is None or canonical_provider(saved.provider) != provider:
            selectable_provider_capability(provider, "llm")
        else:
            provider_capability(provider, "llm", allow_legacy_llm=True)
        profile = self._draft_profile(payload, saved, provider)
        try:
            await ProviderLlmClient(
                self.settings,
                self.cipher,
                timeout_seconds=CONNECTION_TEST_TIMEOUT_SECONDS,
            ).complete(profile, (ChatMessage(role="user", content="Reply with OK."),))
        except ModelProviderError as error:
            raise connection_test_failed(error) from error
        return ModelConnectionTestView(connected=True)

    async def _clear_default(self, tenant_id: str) -> None:
        await self.session.execute(
            update(LlmConfig).where(LlmConfig.tenant_id == tenant_id).values(is_default=False)
        )

    async def _get(self, tenant_id: str, config_id: str) -> LlmConfig:
        model = await self.session.scalar(
            select(LlmConfig).where(LlmConfig.tenant_id == tenant_id, LlmConfig.id == config_id)
        )
        if model is None:
            raise AppError("RESOURCE_NOT_FOUND", "LLM config not found", status.HTTP_404_NOT_FOUND)
        return model

    async def _enter(self, principal: PrincipalContext, tenant_id: str, permission: str) -> None:
        if (
            principal.tenant_id != tenant_id
            and PLATFORM_TENANTS_MANAGE not in principal.permissions
        ):
            raise AppError("RESOURCE_NOT_FOUND", "LLM config not found", status.HTTP_404_NOT_FOUND)
        if permission not in principal.permissions:
            raise AppError("FORBIDDEN", "Permission denied", status.HTTP_403_FORBIDDEN)
        await self.database.set_tenant(self.session, tenant_id)

    def _draft_profile(
        self,
        payload: LlmConfigConnectionTestRequest,
        saved: LlmConfig | None,
        provider: str,
    ) -> RuntimeLlmProfile:
        profile_id = saved.id if saved is not None and payload.api_key is None else "llm_draft_test"
        envelope = saved.credential_envelope if saved is not None else None
        if payload.api_key is not None:
            envelope = self.cipher.encrypt(
                payload.api_key.get_secret_value(), context=llm_credential_context(profile_id)
            )
        return RuntimeLlmProfile(
            id=profile_id,
            provider=provider,
            model=payload.model.strip(),
            base_url=self._endpoint(provider, payload.base_url),
            credential_envelope=envelope,
            temperature=payload.temperature,
            max_tokens=payload.max_tokens,
            thinking_enabled=payload.thinking_enabled,
            prompt_cache_enabled=payload.prompt_cache_enabled,
        )

    def _endpoint(self, provider: str, value: str) -> str:
        capability = provider_capability(provider, "llm", allow_legacy_llm=True)
        return validate_model_endpoint(
            value,
            allowed_hosts=self.settings.ai.allowed_model_hosts,
            trusted_hosts=capability.trusted_hosts,
            trusted_host_suffixes=capability.trusted_host_suffixes,
            production=self.settings.app.environment == "prod",
            resource_label="LLM",
        )

    @staticmethod
    def view(item: LlmConfig) -> LlmConfigView:
        return LlmConfigView(
            id=item.id,
            tenant_id=item.tenant_id,
            name=item.name,
            provider=item.provider,
            model=item.model,
            base_url=item.base_url,
            credential_configured=bool(item.credential_envelope),
            temperature=item.temperature,
            max_tokens=item.max_tokens,
            thinking_enabled=item.thinking_enabled,
            prompt_cache_enabled=item.prompt_cache_enabled,
            status=item.status,
            is_default=item.is_default,
        )


def _audit_values(values: dict[str, object], *, credential_changed: bool) -> dict[str, object]:
    safe = {key: value for key, value in values.items() if key != "credential_envelope"}
    if credential_changed:
        safe["credential_updated"] = True
    return safe


def _has_configured_endpoint(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())
