from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent_runtime import RuntimeLlmProfile
from app.modules.llm_configs.models import LlmConfig


class LlmRuntimeCatalog:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_active(self, tenant_id: str, config_id: str) -> RuntimeLlmProfile | None:
        item = await self.session.scalar(
            select(LlmConfig).where(
                LlmConfig.tenant_id == tenant_id,
                LlmConfig.id == config_id,
                LlmConfig.status == "active",
            )
        )
        if item is None:
            return None
        return RuntimeLlmProfile(
            id=item.id,
            provider=item.provider,
            model=item.model,
            base_url=item.base_url,
            credential_envelope=item.credential_envelope,
            temperature=item.temperature,
            max_tokens=item.max_tokens,
            thinking_enabled=item.thinking_enabled,
            prompt_cache_enabled=item.prompt_cache_enabled,
        )
