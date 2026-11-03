from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.config import AppConfig
from app.core.errors import AppError
from app.core.ids import new_id
from app.infrastructure.credential_cipher import CredentialCipher, reranker_credential_context
from app.infrastructure.db.session import DatabaseManager
from app.modules.audit.service import append_audit
from app.modules.iam.permissions import PLATFORM_TENANTS_MANAGE
from app.modules.iam.schemas import PrincipalContext
from app.modules.knowledge.merge_settings_repository import KnowledgeMergeSettingsRepository
from app.modules.knowledge.models import KnowledgeSpace
from app.modules.knowledge.retrieval_clients import ConfiguredReranker
from app.modules.model_configs.connection_test import (
    CONNECTION_TEST_TIMEOUT_SECONDS,
    connection_test_failed,
)
from app.modules.model_configs.endpoint_policy import validate_model_endpoint
from app.modules.model_configs.schemas import ModelConnectionTestView
from app.modules.model_providers.catalog import (
    CredentialType,
    canonical_provider,
    provider_capability,
    selectable_provider_capability,
)
from app.modules.model_providers.reranker import ProviderRerankerClient, RerankerProviderProfile
from app.modules.model_providers.reranker_credentials import (
    RerankerCredentialError,
    RerankerProviderCredential,
    build_reranker_credential,
    decode_reranker_credential,
    encode_reranker_credential,
)
from app.modules.reranker_configs.models import RerankerConfig
from app.modules.reranker_configs.schemas import (
    RerankerConfigConnectionTestRequest,
    RerankerConfigCreateRequest,
    RerankerConfigUpdateRequest,
    RerankerConfigView,
)


class RerankerConfigService:
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
    ) -> list[RerankerConfigView]:
        await self._enter(principal, tenant_id, "llm_configs.read")
        statement = select(RerankerConfig).where(RerankerConfig.tenant_id == tenant_id)
        if normalized := query.strip() if query else "":
            statement = statement.where(
                or_(
                    RerankerConfig.name.icontains(normalized, autoescape=True),
                    RerankerConfig.provider.icontains(normalized, autoescape=True),
                    RerankerConfig.model.icontains(normalized, autoescape=True),
                )
            )
        rows = await self.session.scalars(
            statement.order_by(RerankerConfig.name, RerankerConfig.id)
        )
        return [self.view(row) for row in rows]

    async def create(
        self, principal: PrincipalContext, tenant_id: str, payload: RerankerConfigCreateRequest
    ) -> RerankerConfigView:
        await self._enter(principal, tenant_id, "llm_configs.manage")
        config_id = new_id("reranker")
        provider = canonical_provider(payload.provider)
        capability = selectable_provider_capability(provider, "reranker")
        credential = self._payload_credential(payload, capability.credential_type)
        item = RerankerConfig(
            id=config_id,
            tenant_id=tenant_id,
            name=payload.name.strip(),
            provider=provider,
            model=payload.model.strip(),
            base_url=self._endpoint(provider, payload.base_url),
            credential_envelope=self.cipher.encrypt(
                encode_reranker_credential(credential),
                context=reranker_credential_context(config_id),
            ),
        )
        self.session.add(item)
        await self.session.flush()
        append_audit(
            self.session,
            principal,
            "reranker_config.create",
            "reranker_config",
            item.id,
            tenant_id=tenant_id,
        )
        return self.view(item)

    async def update(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        config_id: str,
        payload: RerankerConfigUpdateRequest,
    ) -> RerankerConfigView:
        await self._enter(principal, tenant_id, "llm_configs.manage")
        item = await self._get(tenant_id, config_id)
        values, provider, provider_changed = self._update_values(item, payload)
        credential_updated = self._has_payload_credential(payload)
        if provider_changed and not credential_updated:
            capability = provider_capability(provider, "reranker")
            required_field = self._required_credential_field(capability.credential_type)
            raise self._credential_error(required_field)
        if credential_updated:
            capability = provider_capability(provider, "reranker")
            credential = self._payload_credential(payload, capability.credential_type)
            values["credential_envelope"] = self.cipher.encrypt(
                encode_reranker_credential(credential),
                context=reranker_credential_context(item.id),
            )
        if values.get("status") == "disabled" and await self._in_use(tenant_id, item.id):
            raise AppError(
                "RERANKER_CONFIG_IN_USE",
                "Reranker config is used by a knowledge space; rebind it before disabling",
                status.HTTP_409_CONFLICT,
            )
        for key, value in values.items():
            setattr(item, key, value)
        await self.session.flush()
        safe = {key: value for key, value in values.items() if key != "credential_envelope"}
        if credential_updated:
            safe["credential_updated"] = True
        append_audit(
            self.session,
            principal,
            "reranker_config.update",
            "reranker_config",
            item.id,
            safe,
            tenant_id=tenant_id,
        )
        return self.view(item)

    def _update_values(
        self, item: RerankerConfig, payload: RerankerConfigUpdateRequest
    ) -> tuple[dict[str, object], str, bool]:
        credential_fields = {"api_key", "access_key_id", "secret_access_key"}
        values = payload.model_dump(exclude_unset=True, exclude=credential_fields)
        provider = canonical_provider(str(values.get("provider", item.provider)))
        provider_changed = provider != canonical_provider(item.provider)
        if "provider" in values:
            values["provider"] = provider if provider_changed else item.provider
        if provider_changed:
            capability = selectable_provider_capability(provider, "reranker")
            if "model" not in values and capability.default_model is not None:
                values["model"] = capability.default_model
            if "base_url" not in values:
                if capability.default_base_url is None:
                    raise AppError(
                        "MODEL_CONFIG_ENDPOINT_INVALID",
                        "Changing provider requires its model endpoint",
                        status.HTTP_422_UNPROCESSABLE_CONTENT,
                    )
                values["base_url"] = capability.default_base_url
        if "base_url" in values:
            values["base_url"] = self._endpoint(provider, str(values["base_url"]))
        return values, provider, provider_changed

    async def test_connection(
        self, principal: PrincipalContext, tenant_id: str, config_id: str
    ) -> ModelConnectionTestView:
        await self._enter(principal, tenant_id, "llm_configs.manage")
        item = await self._get(tenant_id, config_id)
        try:
            await ConfiguredReranker(
                self.settings,
                self.cipher,
                item,
                timeout_seconds=CONNECTION_TEST_TIMEOUT_SECONDS,
            ).rerank(
                "connection test",
                ("connection test",),
                1,
            )
        except RuntimeError as error:
            raise connection_test_failed(error) from error
        return ModelConnectionTestView(connected=True)

    async def test_draft_connection(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        payload: RerankerConfigConnectionTestRequest,
    ) -> ModelConnectionTestView:
        await self._enter(principal, tenant_id, "llm_configs.manage")
        saved = await self._get(tenant_id, payload.config_id) if payload.config_id else None
        provider = canonical_provider(payload.provider)
        if saved is None or canonical_provider(saved.provider) != provider:
            selectable_provider_capability(provider, "reranker")
        else:
            provider_capability(provider, "reranker")
        capability = provider_capability(provider, "reranker")
        saved_matches = saved is not None and canonical_provider(saved.provider) == provider
        if not saved_matches and not self._has_payload_credential(payload):
            raise self._credential_error(
                self._required_credential_field(capability.credential_type)
            )
        credential = self._test_credential(
            payload,
            saved if saved_matches else None,
            capability.credential_type,
        )
        try:
            await ProviderRerankerClient(
                RerankerProviderProfile(
                    provider=provider,
                    model=payload.model.strip(),
                    base_url=self._endpoint(provider, payload.base_url),
                    credential=credential,
                ),
                timeout_seconds=CONNECTION_TEST_TIMEOUT_SECONDS,
            ).rerank("connection test", ("connection test",), 1)
        except RuntimeError as error:
            raise connection_test_failed(error) from error
        return ModelConnectionTestView(connected=True)

    async def active(self, tenant_id: str, config_id: str) -> RerankerConfig | None:
        return await self.session.scalar(
            select(RerankerConfig).where(
                RerankerConfig.tenant_id == tenant_id,
                RerankerConfig.id == config_id,
                RerankerConfig.status == "active",
            )
        )

    async def _get(self, tenant_id: str, config_id: str) -> RerankerConfig:
        item = await self.session.scalar(
            select(RerankerConfig).where(
                RerankerConfig.tenant_id == tenant_id, RerankerConfig.id == config_id
            )
        )
        if item is None:
            raise AppError(
                "RESOURCE_NOT_FOUND", "Reranker config not found", status.HTTP_404_NOT_FOUND
            )
        return item

    async def _in_use(self, tenant_id: str, config_id: str) -> bool:
        space_reference = await self.session.scalar(
            select(KnowledgeSpace.id).where(
                KnowledgeSpace.tenant_id == tenant_id,
                KnowledgeSpace.reranker_config_id == config_id,
            )
        )
        if space_reference is not None:
            return True
        return await KnowledgeMergeSettingsRepository(self.session).reranker_in_use(
            tenant_id, config_id
        )

    async def _enter(self, principal: PrincipalContext, tenant_id: str, permission: str) -> None:
        if (
            principal.tenant_id != tenant_id
            and PLATFORM_TENANTS_MANAGE not in principal.permissions
        ):
            raise AppError(
                "RESOURCE_NOT_FOUND", "Reranker config not found", status.HTTP_404_NOT_FOUND
            )
        if permission not in principal.permissions:
            raise AppError("FORBIDDEN", "Permission denied", status.HTTP_403_FORBIDDEN)
        await self.database.set_tenant(self.session, tenant_id)

    def _test_credential(
        self,
        payload: RerankerConfigConnectionTestRequest,
        saved: RerankerConfig | None,
        credential_type: CredentialType,
    ) -> RerankerProviderCredential:
        if self._has_payload_credential(payload):
            return self._payload_credential(payload, credential_type)
        if saved is None or not saved.credential_envelope:
            raise connection_test_failed()
        try:
            decrypted = self.cipher.decrypt(
                saved.credential_envelope,
                context=reranker_credential_context(saved.id),
            )
            return decode_reranker_credential(decrypted, credential_type)
        except (RuntimeError, RerankerCredentialError) as error:
            raise connection_test_failed(error) from error

    @staticmethod
    def _has_payload_credential(
        payload: RerankerConfigCreateRequest
        | RerankerConfigUpdateRequest
        | RerankerConfigConnectionTestRequest,
    ) -> bool:
        return any(
            value is not None
            for value in (payload.api_key, payload.access_key_id, payload.secret_access_key)
        )

    @staticmethod
    def _payload_credential(
        payload: RerankerConfigCreateRequest
        | RerankerConfigUpdateRequest
        | RerankerConfigConnectionTestRequest,
        credential_type: CredentialType,
    ) -> RerankerProviderCredential:
        try:
            return build_reranker_credential(
                credential_type,
                api_key=payload.api_key.get_secret_value() if payload.api_key else None,
                access_key_id=(
                    payload.access_key_id.get_secret_value() if payload.access_key_id else None
                ),
                secret_access_key=(
                    payload.secret_access_key.get_secret_value()
                    if payload.secret_access_key
                    else None
                ),
            )
        except RerankerCredentialError as error:
            raise RerankerConfigService._credential_error(error.field) from error

    @staticmethod
    def _credential_error(field: str) -> AppError:
        return AppError(
            "MODEL_PROVIDER_CREDENTIAL_INVALID",
            "Model provider credentials do not match the selected provider",
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            details=[{"field": field, "reason": "Required by the selected provider"}],
        )

    @staticmethod
    def _required_credential_field(credential_type: CredentialType) -> str:
        return "api_key" if credential_type == "api_key" else "access_key_id"

    def _endpoint(self, provider: str, value: str) -> str:
        capability = provider_capability(provider, "reranker")
        return validate_model_endpoint(
            value,
            allowed_hosts=self.settings.knowledge.reranker.allowed_hosts,
            trusted_hosts=capability.trusted_hosts,
            trusted_host_suffixes=capability.trusted_host_suffixes,
            production=self.settings.app.environment == "prod",
            resource_label="Reranker",
        )

    @staticmethod
    def view(item: RerankerConfig) -> RerankerConfigView:
        return RerankerConfigView(
            id=item.id,
            tenant_id=item.tenant_id,
            name=item.name,
            provider=item.provider,
            model=item.model,
            base_url=item.base_url,
            credential_configured=bool(item.credential_envelope),
            status=item.status,
        )
