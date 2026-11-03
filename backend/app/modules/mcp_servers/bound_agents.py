from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class McpBoundAgent:
    id: str
    name: str


class McpBoundAgentReader(Protocol):
    async def list_bound_agents(
        self, tenant_id: str, server_ids: tuple[str, ...]
    ) -> Mapping[str, tuple[McpBoundAgent, ...]]: ...
