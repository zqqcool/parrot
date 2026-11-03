from __future__ import annotations

from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.agent_runtime import RuntimeMcpServerProfile, RuntimeMcpToolPolicy
from app.core.errors import AppError
from app.modules.mcp_servers.models import McpServer


class McpRuntimeCatalog:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_active(
        self, tenant_id: str, server_ids: tuple[str, ...]
    ) -> tuple[RuntimeMcpServerProfile, ...]:
        if not server_ids:
            return ()
        rows = await self.session.scalars(
            select(McpServer).where(
                McpServer.status == "active",
                McpServer.tenant_id == tenant_id,
                McpServer.id.in_(server_ids),
            )
        )
        bound_servers: dict[str, RuntimeMcpServerProfile] = {}
        for item in rows:
            profile = runtime_profile(item)
            bound_servers[item.id] = profile
        return tuple(
            bound_servers[server_id] for server_id in server_ids if server_id in bound_servers
        )

    async def validate_ids(self, tenant_id: str, ids: tuple[str, ...]) -> None:
        if not ids:
            return
        found = await self.session.scalars(
            select(McpServer.id).where(
                McpServer.tenant_id == tenant_id,
                McpServer.id.in_(ids),
                McpServer.status == "active",
            )
        )
        if set(found) != set(ids):
            raise AppError(
                "MCP_SERVER_NOT_FOUND",
                "One or more active MCP servers are unavailable",
                status.HTTP_404_NOT_FOUND,
            )


def runtime_profile(item: McpServer) -> RuntimeMcpServerProfile:
    return RuntimeMcpServerProfile(
        id=item.id,
        name=item.name,
        transport=item.transport,
        endpoint=item.endpoint,
        arguments=tuple(item.arguments),
        encrypted_credentials=tuple(item.encrypted_credentials),
        tool_policies=tuple(
            RuntimeMcpToolPolicy(
                name=str(policy["name"]),
                description=str(policy.get("description", "")),
                input_schema=cast(dict[str, object], policy["input_schema"]),
                schema_hash=str(policy["schema_hash"]),
                effect=str(policy["effect"]),
                approval=str(policy["approval"]),
                parallel_safe=policy.get("parallel_safe") is True,
            )
            for policy in (item.tool_policies or [])
        ),
    )
