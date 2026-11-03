from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.config import AppConfig
from app.core.errors import AppError
from app.core.ids import new_id
from app.infrastructure.credential_cipher import CredentialCipher, embedding_credential_context
from app.infrastructure.db.session import DatabaseManager
from app.modules.audit.service import append_audit
from app.modules.embedding_configs.models import EmbeddingConfig
from app.modules.embedding_configs.schemas import (
    EmbeddingConfigConnectionTestRequest,
    EmbeddingConfigCreateRequest,
    EmbeddingConfigUpdateRequest,
    EmbeddingConfigView,
)
from app.modules.iam.permissions import PLATFORM_TENANTS_MANAGE
from app.modules.iam.schemas import PrincipalContext
from app.modules.knowledge.embedding import KnowledgeEmbeddingError
from app.modules.knowledge.models import (
    KnowledgeSpace,
    KnowledgeVectorIndexJob,
    KnowledgeVectorReference,
)
from app.modules.knowledge.retrieval_clients import ConfiguredKnowledgeEmbedding
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
from app.modules.model_providers.embedding import (
    EmbeddingProviderProfile,
    ProviderEmbeddingClient,
    ProviderEmbeddingError,
)


class EmbeddingConfigService:
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
    ) -> list[EmbeddingConfigView]:
        await self._enter(principal, tenant_id, "llm_configs.read")
        statement = select(EmbeddingConfig, func.count(KnowledgeSpace.id)).where(
            EmbeddingConfig.tenant_id == tenant_id
        )
        if normalized := query.strip() if query else "":
            statement = statement.where(
                or_(
                    EmbeddingConfig.name.icontains(normalized, autoescape=True),
                    EmbeddingConfig.provider.icontains(normalized, autoescape=True),
                    EmbeddingConfig.model.icontains(normalized, autoescape=True),
                )
            )
        rows = await self.session.execute(
            statement.outerjoin(
                KnowledgeSpace,
                (KnowledgeSpace.tenant_id == EmbeddingConfig.tenant_id)
                & (KnowledgeSpace.embedding_config_id == EmbeddingConfig.id),
            )
            .group_by(EmbeddingConfig.id)
            .order_by(EmbeddingConfig.name, EmbeddingConfig.id)
        )
        return [
            self.view(
                item,
                reference_count,
                await self._can_delete(tenant_id, item.id, reference_count),
            )
            for item, reference_count in rows
        ]

    async def create(
        self, principal: PrincipalContext, tenant_id: str, payload: EmbeddingConfigCreateRequest
    ) -> EmbeddingConfigView:
        await self._enter(principal, tenant_id, "llm_configs.manage")
        config_id = new_id("embedding")
        provider = canonical_provider(payload.provider)
        selectable_provider_capability(provider, "embedding")
        endpoint = self._endpoint(provider, payload.base_url)
        item = EmbeddingConfig(
            id=config_id,
            tenant_id=tenant_id,
            name=payload.name.strip(),
            provider=provider,
            model=payload.model.strip(),
            base_url=endpoint,
            credential_envelope=self.cipher.encrypt(
                payload.api_key.get_secret_value(), context=embedding_credential_context(config_id)
            ),
            embedding_dimension=payload.embedding_dimension,
            configuration_version=1,
        )
        self.session.add(item)
        await self.session.flush()
        append_audit(
            self.session,
            principal,
            "embedding_config.create",
            "embedding_config",
            item.id,
            tenant_id=tenant_id,
        )
        return self.view(item, 0, True)

    async def update(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        config_id: str,
        payload: EmbeddingConfigUpdateRequest,
    ) -> EmbeddingConfigView:
        await self._enter(principal, tenant_id, "llm_configs.manage")
        item = await self._get(tenant_id, config_id)
        values = payload.model_dump(exclude_unset=True, exclude={"api_key"})
        provider = canonical_provider(str(values.get("provider", item.provider)))
        if "provider" in values:
            current_provider = canonical_provider(item.provider)
            if provider != current_provider:
                selectable_provider_capability(provider, "embedding")
            values["provider"] = provider if provider != current_provider else item.provider
        if "base_url" in values:
            values["base_url"] = self._endpoint(provider, str(values["base_url"]))
        values = {key: value for key, value in values.items() if getattr(item, key) != value}
        if payload.api_key is not None:
            values["credential_envelope"] = self.cipher.encrypt(
                payload.api_key.get_secret_value(), context=embedding_credential_context(item.id)
            )
        changed_identity = any(
            key in values for key in ("provider", "base_url", "model", "embedding_dimension")
        )
        if changed_identity:
            raise AppError(
                "EMBEDDING_CONFIG_IDENTITY_IMMUTABLE",
                "Create a new Embedding config to change provider, endpoint, model or dimension",
                status.HTTP_409_CONFLICT,
            )
        for key, value in values.items():
            setattr(item, key, value)
        await self.session.flush()
        safe = {key: value for key, value in values.items() if key != "credential_envelope"}
        if payload.api_key is not None:
            safe["credential_updated"] = True
        append_audit(
            self.session,
            principal,
            "embedding_config.update",
            "embedding_config",
            item.id,
            safe,
            tenant_id=tenant_id,
        )
        reference_count = await self._reference_count(tenant_id, item.id)
        return self.view(
            item,
            reference_count,
            await self._can_delete(tenant_id, item.id, reference_count),
        )

    async def delete(self, principal: PrincipalContext, tenant_id: str, config_id: str) -> None:
        await self._enter(principal, tenant_id, "llm_configs.manage")
        item = await self._get(tenant_id, config_id)
        reference_count = await self._reference_count(tenant_id, item.id)
        if not await self._can_delete(tenant_id, item.id, reference_count):
            raise AppError(
                "EMBEDDING_CONFIG_IN_USE",
                "Embedding config is referenced by knowledge data and cannot be deleted",
                status.HTTP_409_CONFLICT,
            )
        await self.session.delete(item)
        await self.session.flush()
        append_audit(
            self.session,
            principal,
            "embedding_config.delete",
            "embedding_config",
            item.id,
            tenant_id=tenant_id,
        )

    async def test_connection(
        self, principal: PrincipalContext, tenant_id: str, config_id: str
    ) -> ModelConnectionTestView:
        await self._enter(principal, tenant_id, "llm_configs.manage")
        item = await self._get(tenant_id, config_id)
        try:
            await ConfiguredKnowledgeEmbedding(
                self.settings,
                self.cipher,
                item,
                timeout_seconds=CONNECTION_TEST_TIMEOUT_SECONDS,
            ).embed(("connection test",))
        except (KnowledgeEmbeddingError, RuntimeError) as error:
            raise connection_test_failed(error) from error
        return ModelConnectionTestView(connected=True)

    async def test_draft_connection(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        payload: EmbeddingConfigConnectionTestRequest,
    ) -> ModelConnectionTestView:
        await self._enter(principal, tenant_id, "llm_configs.manage")
        saved = await self._get(tenant_id, payload.config_id) if payload.config_id else None
        provider = canonical_provider(payload.provider)
        if saved is None or canonical_provider(saved.provider) != provider:
            selectable_provider_capability(provider, "embedding")
        else:
            provider_capability(provider, "embedding")
        credential = self._test_credential(payload, saved)
        try:
            await ProviderEmbeddingClient(
                EmbeddingProviderProfile(
                    provider=provider,
                    model=payload.model.strip(),
                    base_url=self._endpoint(provider, payload.base_url),
                    api_key=credential,
                    embedding_dimension=payload.embedding_dimension,
                ),
                timeout_seconds=CONNECTION_TEST_TIMEOUT_SECONDS,
            ).embed(("connection test",))
        except ProviderEmbeddingError as error:
            raise connection_test_failed(error) from error
        return ModelConnectionTestView(connected=True)

    async def active(self, tenant_id: str, config_id: str) -> EmbeddingConfig | None:
        return await self.session.scalar(
            select(EmbeddingConfig).where(
                EmbeddingConfig.tenant_id == tenant_id,
                EmbeddingConfig.id == config_id,
                EmbeddingConfig.status == "active",
            )
        )

    async def _get(self, tenant_id: str, config_id: str) -> EmbeddingConfig:
        item = await self.session.scalar(
            select(EmbeddingConfig).where(
                EmbeddingConfig.tenant_id == tenant_id, EmbeddingConfig.id == config_id
            )
        )
        if item is None:
            raise AppError(
                "RESOURCE_NOT_FOUND", "Embedding config not found", status.HTTP_404_NOT_FOUND
            )
        return item

    async def _reference_count(self, tenant_id: str, config_id: str) -> int:
        return int(
            await self.session.scalar(
                select(func.count(KnowledgeSpace.id)).where(
                    KnowledgeSpace.tenant_id == tenant_id,
                    KnowledgeSpace.embedding_config_id == config_id,
                )
            )
            or 0
        )

    async def _can_delete(
        self, tenant_id: str, config_id: str, knowledge_space_references: int
    ) -> bool:
        if knowledge_space_references:
            return False
        for model in (KnowledgeVectorIndexJob, KnowledgeVectorReference):
            dependent = await self.session.scalar(
                select(model.id).where(
                    model.tenant_id == tenant_id,
                    model.embedding_config_id == config_id,
                )
            )
            if dependent is not None:
                return False
        return True

    async def _enter(self, principal: PrincipalContext, tenant_id: str, permission: str) -> None:
        if (
            principal.tenant_id != tenant_id
            and PLATFORM_TENANTS_MANAGE not in principal.permissions
        ):
            raise AppError(
                "RESOURCE_NOT_FOUND", "Embedding config not found", status.HTTP_404_NOT_FOUND
            )
        if permission not in principal.permissions:
            raise AppError("FORBIDDEN", "Permission denied", status.HTTP_403_FORBIDDEN)
        await self.database.set_tenant(self.session, tenant_id)

    def _test_credential(
        self,
        payload: EmbeddingConfigConnectionTestRequest,
        saved: EmbeddingConfig | None,
    ) -> str:
        if payload.api_key is not None:
            return payload.api_key.get_secret_value()
        if saved is None or not saved.credential_envelope:
            raise connection_test_failed()
        try:
            return self.cipher.decrypt(
                saved.credential_envelope, context=embedding_credential_context(saved.id)
            )
        except RuntimeError as error:
            raise connection_test_failed(error) from error

    def _endpoint(self, provider: str, value: str) -> str:
        capability = provider_capability(provider, "embedding")
        return validate_model_endpoint(
            value,
            allowed_hosts=self.settings.knowledge.embedding.allowed_hosts,
            trusted_hosts=capability.trusted_hosts,
            trusted_host_suffixes=capability.trusted_host_suffixes,
            production=self.settings.app.environment == "prod",
            resource_label="Embedding",
        )

    @staticmethod
    def view(item: EmbeddingConfig, reference_count: int, can_delete: bool) -> EmbeddingConfigView:
        return EmbeddingConfigView(
            id=item.id,
            tenant_id=item.tenant_id,
            name=item.name,
            provider=item.provider,
            model=item.model,
            base_url=item.base_url,
            credential_configured=bool(item.credential_envelope),
            embedding_dimension=item.embedding_dimension,
            configuration_version=item.configuration_version,
            status=item.status,
            reference_count=reference_count,
            can_delete=can_delete,
        )
