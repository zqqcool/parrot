from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.errors import AppError
from app.infrastructure.db.session import DatabaseManager
from app.modules.iam.permissions import LLM_CONFIGS_READ, PLATFORM_TENANTS_MANAGE
from app.modules.iam.schemas import PrincipalContext
from app.modules.model_providers.catalog import providers
from app.modules.model_providers.schemas import (
    ModelProviderCapabilityView,
    ModelProviderView,
)


class ModelProviderCatalogService:
    def __init__(self, session: AsyncSession, database: DatabaseManager) -> None:
        self._session = session
        self._database = database

    async def list(self, principal: PrincipalContext, tenant_id: str) -> list[ModelProviderView]:
        if (
            principal.tenant_id != tenant_id
            and PLATFORM_TENANTS_MANAGE not in principal.permissions
        ):
            raise AppError("RESOURCE_NOT_FOUND", "Tenant not found", status.HTTP_404_NOT_FOUND)
        if LLM_CONFIGS_READ not in principal.permissions:
            raise AppError("FORBIDDEN", "Permission denied", status.HTTP_403_FORBIDDEN)
        await self._database.set_tenant(self._session, tenant_id)
        return [
            ModelProviderView(
                key=provider.key,
                name=provider.name,
                capabilities=[
                    ModelProviderCapabilityView(
                        kind=capability.kind,
                        description=capability.description,
                        credential_type=capability.credential_type,
                        default_base_url=capability.default_base_url,
                        default_model=capability.default_model,
                        default_embedding_dimension=capability.default_embedding_dimension,
                        base_url_placeholder=capability.base_url_placeholder,
                        model_placeholder=capability.model_placeholder,
                    )
                    for capability in provider.capabilities
                ],
            )
            for provider in providers()
        ]
