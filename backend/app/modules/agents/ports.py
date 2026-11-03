from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class CapabilityCatalogPort(Protocol):
    async def validate_ids(self, tenant_id: str, ids: tuple[str, ...]) -> None: ...


class SkillCatalogPort(CapabilityCatalogPort, Protocol):
    async def validate_instruction_only_ids(self, tenant_id: str, ids: tuple[str, ...]) -> None: ...


class AgentPublicationPolicy(Protocol):
    async def ensure_publishable(self, tenant_id: str, agent_id: str) -> None: ...

    async def ensure_agent_type_change_allowed(
        self, tenant_id: str, agent_id: str, agent_type_key: str
    ) -> None: ...


@dataclass(frozen=True)
class AgentAvatar:
    content: bytes
    content_type: str


@dataclass(frozen=True)
class AgentRuntimeTarget:
    id: str
    tenant_id: str
    runtime_agent_id: str


class AgentCatalogPort(Protocol):
    async def exists(self, tenant_id: str, agent_id: str) -> bool: ...

    async def get_published(self, tenant_id: str, agent_id: str) -> AgentRuntimeTarget | None: ...

    async def names(self, tenant_id: str, agent_ids: tuple[str, ...]) -> dict[str, str]: ...
