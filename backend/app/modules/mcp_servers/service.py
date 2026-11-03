from __future__ import annotations

from collections.abc import Mapping
from typing import Literal, cast

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.errors import AppError
from app.core.ids import new_id
from app.core.task_dispatch import TaskDispatcher
from app.infrastructure.credential_cipher import CredentialCipher, mcp_credential_context
from app.infrastructure.db.session import DatabaseManager
from app.modules.agent_runtime.mcp_executor import McpExecutor
from app.modules.audit.service import append_audit
from app.modules.capabilities.authorization import enter_tenant_capability_scope
from app.modules.iam.permissions import AGENTS_READ
from app.modules.iam.schemas import PrincipalContext, UserReference
from app.modules.iam.user_references import UserReferenceResolver
from app.modules.mcp_servers.bound_agents import McpBoundAgent, McpBoundAgentReader
from app.modules.mcp_servers.models import McpServer
from app.modules.mcp_servers.runtime_catalog import runtime_profile
from app.modules.mcp_servers.schemas import (
    McpBoundAgentView,
    McpCredentialCreate,
    McpCredentialUpdate,
    McpCredentialView,
    McpDiscoveredToolView,
    McpServerCreateRequest,
    McpServerUpdateRequest,
    McpServerView,
    McpToolPolicyInput,
    McpToolPolicyView,
)
from app.modules.mcp_servers.tool_policy import mcp_schema_hash


class McpServerService:
    def __init__(
        self,
        session: AsyncSession,
        database: DatabaseManager,
        cipher: CredentialCipher,
        bound_agent_reader: McpBoundAgentReader | None = None,
        dispatcher: TaskDispatcher | None = None,
        mcp_executor: McpExecutor | None = None,
    ) -> None:
        self.session = session
        self.database = database
        self.cipher = cipher
        self.bound_agent_reader = bound_agent_reader
        self._dispatcher = dispatcher
        self._mcp_executor = mcp_executor

    async def list(
        self, principal: PrincipalContext, tenant_id: str, *, query: str | None = None
    ) -> list[McpServerView]:
        await self._enter(principal, tenant_id, "mcp_servers.read")
        statement = select(McpServer).where(McpServer.tenant_id == tenant_id)
        normalized = query.strip() if query else ""
        if normalized:
            statement = statement.where(
                or_(
                    McpServer.name.icontains(normalized, autoescape=True),
                    McpServer.transport.icontains(normalized, autoescape=True),
                    McpServer.endpoint.icontains(normalized, autoescape=True),
                )
            )
        rows = await self.session.scalars(statement.order_by(McpServer.name))
        return await self._views(principal, list(rows))

    async def create(
        self, principal: PrincipalContext, tenant_id: str, payload: McpServerCreateRequest
    ) -> McpServerView:
        await self._enter(principal, tenant_id, "mcp_servers.manage")
        _validate_credential_targets(payload.transport, payload.credentials)
        server_id = new_id("mcp")
        model = McpServer(
            id=server_id,
            tenant_id=tenant_id,
            created_by=principal.subject_id,
            encrypted_credentials=self._encrypt_credentials(server_id, payload.credentials),
            tool_policies=_policy_values(payload.tool_policies),
            **payload.model_dump(exclude={"credentials", "tool_policies"}),
        )
        self.session.add(model)
        await self.session.flush()
        await self._enqueue_index(model)
        append_audit(
            self.session,
            principal,
            "mcp_server.create",
            "mcp_server",
            model.id,
            tenant_id=tenant_id,
        )
        return await self._view(principal, model)

    async def update(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        server_id: str,
        payload: McpServerUpdateRequest,
    ) -> McpServerView:
        await self._enter(principal, tenant_id, "mcp_servers.manage")
        model = await self._get(tenant_id, server_id)
        values = payload.model_dump(exclude_unset=True, exclude={"credentials", "tool_policies"})
        if payload.tool_policies is not None:
            values["tool_policies"] = _policy_values(payload.tool_policies)
        credentials_changed = payload.credentials is not None
        if payload.credentials is not None:
            values["encrypted_credentials"] = self._merge_credentials(
                server_id, model.encrypted_credentials, payload.credentials
            )
        if payload.transport is not None or payload.credentials is not None:
            _validate_credential_targets(
                cast(str, values.get("transport", model.transport)),
                cast(
                    list[dict[str, str]],
                    values.get("encrypted_credentials", model.encrypted_credentials),
                ),
            )
        if values:
            await self.session.execute(
                update(McpServer).where(McpServer.id == server_id).values(**values)
            )
            await self.session.refresh(model)
            await self._enqueue_index(model)
        append_audit(
            self.session,
            principal,
            "mcp_server.update",
            "mcp_server",
            model.id,
            _audit_values(values, credentials_changed=credentials_changed),
            tenant_id=tenant_id,
        )
        return await self._view(principal, model)

    async def discover_tools(
        self, principal: PrincipalContext, tenant_id: str, server_id: str
    ) -> list[McpDiscoveredToolView]:
        await self._enter(principal, tenant_id, "mcp_servers.manage")
        model = await self._get(tenant_id, server_id)
        if self._mcp_executor is None:
            raise AppError(
                "MCP_RUNTIME_UNAVAILABLE",
                "MCP runtime is unavailable",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        tools = await self._mcp_executor.discover((runtime_profile(model),))
        return [
            McpDiscoveredToolView(
                name=tool.tool_name,
                description=tool.description,
                input_schema=tool.input_schema,
                schema_hash=mcp_schema_hash(tool.input_schema),
                read_only_hint=tool.read_only,
            )
            for tool in tools
        ]

    async def _get(self, tenant_id: str, server_id: str) -> McpServer:
        model = await self.session.scalar(
            select(McpServer).where(
                McpServer.tenant_id == tenant_id,
                McpServer.id == server_id,
            )
        )
        if model is None:
            raise AppError("RESOURCE_NOT_FOUND", "MCP server not found", status.HTTP_404_NOT_FOUND)
        return model

    async def _enter(self, principal: PrincipalContext, tenant_id: str, permission: str) -> None:
        await enter_tenant_capability_scope(
            self.database, self.session, principal, tenant_id, permission, "MCP server"
        )

    async def _view(self, principal: PrincipalContext, item: McpServer) -> McpServerView:
        users = await UserReferenceResolver(self.session).resolve(
            item.tenant_id, (item.created_by,)
        )
        bound_agents = await self._bound_agents(principal, item.tenant_id, (item.id,))
        return self.view(
            item,
            users,
            bound_agents.get(item.id, ()) if bound_agents is not None else None,
        )

    async def _views(
        self, principal: PrincipalContext, items: list[McpServer]
    ) -> list[McpServerView]:
        users = await UserReferenceResolver(self.session).resolve(
            items[0].tenant_id if items else None, (item.created_by for item in items)
        )
        tenant_id = items[0].tenant_id if items else ""
        bound_agents = await self._bound_agents(
            principal, tenant_id, tuple(item.id for item in items)
        )
        return [
            self.view(
                item,
                users,
                bound_agents.get(item.id, ()) if bound_agents is not None else None,
            )
            for item in items
        ]

    async def _bound_agents(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        server_ids: tuple[str, ...],
    ) -> Mapping[str, tuple[McpBoundAgent, ...]] | None:
        if AGENTS_READ not in principal.permissions:
            return None
        if not server_ids or self.bound_agent_reader is None:
            return {}
        return await self.bound_agent_reader.list_bound_agents(tenant_id, server_ids)

    @staticmethod
    def view(
        item: McpServer,
        users: Mapping[str, UserReference] | None = None,
        bound_agents: tuple[McpBoundAgent, ...] | None = None,
    ) -> McpServerView:
        return McpServerView(
            id=item.id,
            tenant_id=item.tenant_id,
            created_by_user=(users or {}).get(item.created_by or ""),
            name=item.name,
            transport=item.transport,
            endpoint=item.endpoint,
            arguments=item.arguments,
            credentials=[
                McpCredentialView(
                    target=cast(Literal["env", "header"], value["target"]),
                    name=value["name"],
                )
                for value in item.encrypted_credentials
            ],
            status=item.status,
            tool_policies=[
                McpToolPolicyView.model_validate(policy) for policy in (item.tool_policies or [])
            ],
            bound_agents=(
                tuple(McpBoundAgentView(id=agent.id, name=agent.name) for agent in bound_agents)
                if bound_agents is not None
                else None
            ),
        )

    def _encrypt_credentials(
        self, server_id: str, credentials: list[McpCredentialCreate]
    ) -> list[dict[str, str]]:
        return [self._encrypt_credential(server_id, item) for item in credentials]

    async def _enqueue_index(self, item: McpServer) -> None:
        if self._dispatcher is None:
            return
        await self._dispatcher.dispatch_capability_index(
            item.tenant_id,
            "mcp_server",
            item.id,
            item.updated_at.isoformat(),
        )

    def _merge_credentials(
        self,
        server_id: str,
        existing: list[dict[str, str]],
        credentials: list[McpCredentialUpdate],
    ) -> list[dict[str, str]]:
        stored = {(item["target"], item["name"]): item["envelope"] for item in existing}
        merged: list[dict[str, str]] = []
        for item in credentials:
            if item.secret is not None:
                merged.append(self._encrypt_credential(server_id, item))
                continue
            envelope = stored.get((item.target, item.name))
            if envelope is None:
                raise AppError(
                    "MCP_CREDENTIAL_VALUE_REQUIRED",
                    "A value is required for a new or renamed MCP credential",
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                )
            merged.append({"target": item.target, "name": item.name, "envelope": envelope})
        return merged

    def _encrypt_credential(
        self, server_id: str, item: McpCredentialCreate | McpCredentialUpdate
    ) -> dict[str, str]:
        if item.secret is None:
            raise ValueError("MCP credential value is required")
        return {
            "target": item.target,
            "name": item.name,
            "envelope": self.cipher.encrypt(
                item.secret.get_secret_value(),
                context=mcp_credential_context(server_id, item.target, item.name),
            ),
        }


def _audit_values(values: dict[str, object], *, credentials_changed: bool) -> dict[str, object]:
    safe = {key: value for key, value in values.items() if key != "encrypted_credentials"}
    if credentials_changed:
        safe["credentials_updated"] = True
    return safe


def _policy_values(policies: list[McpToolPolicyInput]) -> list[dict[str, object]]:
    return [
        {
            **policy.model_dump(),
            "schema_hash": mcp_schema_hash(policy.input_schema),
        }
        for policy in policies
    ]


def _validate_credential_targets(
    transport: str, credentials: list[McpCredentialCreate] | list[dict[str, str]]
) -> None:
    expected_target = "env" if transport == "stdio" else "header"
    for credential in credentials:
        target = (
            credential.target
            if isinstance(credential, McpCredentialCreate)
            else credential["target"]
        )
        if target != expected_target:
            raise AppError(
                "MCP_CREDENTIAL_TARGET_INVALID",
                f"{transport} MCP credentials must use {expected_target} targets",
                status.HTTP_422_UNPROCESSABLE_CONTENT,
            )
