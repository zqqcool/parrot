from __future__ import annotations

import asyncio
import json
import logging
import shutil
from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any, Protocol, cast

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client
from pydantic import BaseModel

from app.core.agent_runtime import RuntimeMcpServerProfile
from app.core.config import AppConfig
from app.infrastructure.credential_cipher import (
    CredentialCipher,
    CredentialCipherError,
    mcp_credential_context,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RuntimeMcpTool:
    capability_id: str
    server_id: str
    server_name: str
    tool_name: str
    description: str
    input_schema: dict[str, object]
    read_only: bool = False


class McpExecutor(Protocol):
    async def discover(
        self, servers: tuple[RuntimeMcpServerProfile, ...]
    ) -> tuple[RuntimeMcpTool, ...]: ...

    async def execute(
        self, tool: RuntimeMcpTool, input_payload: dict[str, object]
    ) -> dict[str, object]: ...


class McpClientExecutor:
    """One-shot MCP client that decrypts only persisted server credentials."""

    def __init__(self, settings: AppConfig, cipher: CredentialCipher) -> None:
        self._settings = settings
        self._cipher = cipher
        self._tool_index: dict[str, tuple[RuntimeMcpServerProfile, RuntimeMcpTool]] = {}

    async def discover(
        self, servers: tuple[RuntimeMcpServerProfile, ...]
    ) -> tuple[RuntimeMcpTool, ...]:
        discovered = await asyncio.gather(*(self._discover_server(server) for server in servers))
        return tuple(tool for server_tools in discovered for tool in server_tools)

    async def execute(
        self, tool: RuntimeMcpTool, input_payload: dict[str, object]
    ) -> dict[str, object]:
        selected = self._tool_index.get(tool.capability_id)
        if selected is None:
            return _rejected("MCP_CAPABILITY_NOT_FOUND", "MCP capability must be discovered first")
        server, known_tool = selected
        try:
            async with self._session(server) as session:
                result = await asyncio.wait_for(
                    session.call_tool(
                        known_tool.tool_name,
                        cast(dict[str, Any], input_payload),
                        read_timeout_seconds=timedelta(
                            seconds=self._settings.mcp.tool_timeout_seconds
                        ),
                    ),
                    timeout=self._settings.mcp.tool_timeout_seconds,
                )
        except McpPolicyError as error:
            return _rejected(error.code, error.message)
        except Exception:
            logger.exception("MCP tool execution failed", extra={"mcp_server_id": server.id})
            return _rejected("MCP_EXECUTION_FAILED", "MCP tool execution failed")
        return _tool_result(result, self._settings.mcp.max_tool_result_bytes)

    async def _discover_server(self, server: RuntimeMcpServerProfile) -> tuple[RuntimeMcpTool, ...]:
        try:
            async with self._session(server) as session:
                result = await asyncio.wait_for(
                    session.list_tools(), timeout=self._settings.mcp.connect_timeout_seconds
                )
        except McpPolicyError as error:
            logger.warning(
                "MCP server rejected by policy: %s", error.code, extra={"mcp_server_id": server.id}
            )
            return ()
        except Exception:
            logger.exception("MCP tool discovery failed", extra={"mcp_server_id": server.id})
            return ()
        tools: list[RuntimeMcpTool] = []
        for raw_tool in result.tools[: self._settings.mcp.max_discovered_tools_per_server]:
            tool = _tool_profile(server, raw_tool)
            self._tool_index[tool.capability_id] = (server, tool)
            tools.append(tool)
        return tuple(tools)

    @asynccontextmanager
    async def _session(self, server: RuntimeMcpServerProfile) -> AsyncGenerator[ClientSession]:
        async with AsyncExitStack() as stack:
            read_stream, write_stream = await self._transport(stack, server)
            session = await stack.enter_async_context(ClientSession(read_stream, write_stream))
            await asyncio.wait_for(
                session.initialize(), timeout=self._settings.mcp.connect_timeout_seconds
            )
            yield session

    async def _transport(
        self, stack: AsyncExitStack, server: RuntimeMcpServerProfile
    ) -> tuple[Any, Any]:
        headers, environment = self._credentials(server)
        if server.transport == "streamable_http":
            self._validate_http_endpoint(server.endpoint)
            if environment:
                raise McpPolicyError(
                    "MCP_SECRET_TARGET_INVALID", "HTTP MCP credentials must use header targets"
                )
            client = await stack.enter_async_context(
                httpx.AsyncClient(
                    headers=headers,
                    timeout=self._settings.mcp.connect_timeout_seconds,
                )
            )
            streams = await stack.enter_async_context(
                streamable_http_client(server.endpoint, http_client=client)
            )
            return streams[0], streams[1]
        if server.transport == "sse":
            self._validate_http_endpoint(server.endpoint)
            if environment:
                raise McpPolicyError(
                    "MCP_SECRET_TARGET_INVALID", "HTTP MCP credentials must use header targets"
                )
            streams = await stack.enter_async_context(
                sse_client(
                    server.endpoint,
                    headers=headers,
                    timeout=self._settings.mcp.connect_timeout_seconds,
                )
            )
            return streams[0], streams[1]
        if server.transport == "stdio":
            if not self._settings.mcp.allow_stdio:
                raise McpPolicyError("MCP_STDIO_DISABLED", "stdio MCP is disabled by configuration")
            parameters = self._stdio_parameters(server, environment)
            streams = await stack.enter_async_context(stdio_client(parameters))
            return streams[0], streams[1]
        raise McpPolicyError("MCP_TRANSPORT_UNSUPPORTED", "MCP transport is unsupported")

    def _credentials(
        self, server: RuntimeMcpServerProfile
    ) -> tuple[dict[str, str], dict[str, str]]:
        headers: dict[str, str] = {}
        environment: dict[str, str] = {}
        for encrypted in server.encrypted_credentials:
            target = encrypted.get("target")
            name = encrypted.get("name")
            envelope = encrypted.get("envelope")
            if target not in {"header", "env"} or not name or not envelope:
                raise McpPolicyError("MCP_CREDENTIAL_UNAVAILABLE", "MCP credential is unavailable")
            try:
                value = self._cipher.decrypt(
                    envelope, context=mcp_credential_context(server.id, target, name)
                )
            except CredentialCipherError as error:
                raise McpPolicyError(
                    "MCP_CREDENTIAL_UNAVAILABLE", "MCP credential is unavailable"
                ) from error
            if target == "header":
                headers[name] = value
            else:
                environment[name] = value
        return headers, environment

    def _validate_http_endpoint(self, endpoint: str) -> None:
        try:
            url = httpx.URL(endpoint)
        except ValueError as error:
            raise McpPolicyError("MCP_ENDPOINT_INVALID", "MCP endpoint is invalid") from error
        if url.scheme not in {"http", "https"} or not url.host or url.username or url.password:
            raise McpPolicyError("MCP_ENDPOINT_INVALID", "MCP endpoint is invalid")
        if self._settings.app.environment == "prod" and url.scheme != "https":
            raise McpPolicyError("MCP_ENDPOINT_INVALID", "Production MCP endpoints require HTTPS")
        allowed_hosts = {value.casefold() for value in self._settings.mcp.allowed_hosts}
        if allowed_hosts and url.host.casefold() not in allowed_hosts:
            raise McpPolicyError("MCP_ENDPOINT_NOT_ALLOWED", "MCP endpoint host is not allowlisted")

    def _stdio_parameters(
        self, server: RuntimeMcpServerProfile, environment: dict[str, str]
    ) -> StdioServerParameters:
        sandbox = self._settings.skills.sandbox
        bwrap = shutil.which(sandbox.bwrap_path)
        if sandbox.require_bubblewrap:
            if not bwrap:
                raise McpPolicyError("MCP_SANDBOX_UNAVAILABLE", "MCP sandbox is unavailable")
            return StdioServerParameters(
                command=bwrap,
                args=_bubblewrap_mcp_command(server, environment),
                env={},
            )
        if not sandbox.allow_unsafe_local_execution:
            raise McpPolicyError("MCP_SANDBOX_UNAVAILABLE", "MCP sandbox is unavailable")
        return StdioServerParameters(
            command=server.endpoint,
            args=list(server.arguments),
            env=_minimal_environment(environment),
        )


class McpPolicyError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _tool_profile(server: RuntimeMcpServerProfile, raw_tool: object) -> RuntimeMcpTool:
    name = str(getattr(raw_tool, "name", "")).strip()
    description = str(getattr(raw_tool, "description", "") or "")
    schema = getattr(raw_tool, "inputSchema", {})
    input_schema = cast(dict[str, object], schema) if isinstance(schema, dict) else {}
    return RuntimeMcpTool(
        capability_id=f"mcp:{server.id}:{name}",
        server_id=server.id,
        server_name=server.name,
        tool_name=name,
        description=description,
        input_schema=input_schema,
        read_only=_read_only_hint(raw_tool),
    )


def _read_only_hint(raw_tool: object) -> bool:
    annotations = getattr(raw_tool, "annotations", None)
    if isinstance(annotations, BaseModel):
        raw = cast(dict[str, object], annotations.model_dump(mode="json", by_alias=True))
    elif isinstance(annotations, dict):
        raw = cast(dict[str, object], annotations)
    else:
        return False
    return raw.get("readOnlyHint") is True or raw.get("read_only_hint") is True


def _tool_result(value: object, max_bytes: int) -> dict[str, object]:
    payload = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    try:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    except (TypeError, ValueError):
        return _rejected("MCP_RESULT_INVALID", "MCP returned an invalid tool result")
    if len(encoded) > max_bytes:
        return _rejected("MCP_RESULT_TOO_LARGE", "MCP tool result exceeds the allowed size")
    is_error = bool(getattr(value, "isError", False))
    return {
        "status": "failed" if is_error else "succeeded",
        "result": cast(dict[str, object], payload) if isinstance(payload, dict) else payload,
    }


def _bubblewrap_mcp_command(
    server: RuntimeMcpServerProfile, environment: dict[str, str]
) -> list[str]:
    command = [
        "--die-with-parent",
        "--new-session",
        "--unshare-all",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--tmpfs",
        "/tmp",
    ]
    for path in ("/usr", "/usr/local", "/bin", "/lib", "/lib64", "/etc/ssl/certs"):
        if Path(path).exists():
            command.extend(("--ro-bind", path, path))
    command.extend(
        (
            "--clearenv",
            "--setenv",
            "HOME",
            "/tmp",
            "--setenv",
            "PATH",
            "/usr/local/bin:/usr/bin:/bin",
        )
    )
    for name, value in environment.items():
        command.extend(("--setenv", name, value))
    command.extend(("--", server.endpoint, *server.arguments))
    return command


def _minimal_environment(values: dict[str, str]) -> dict[str, str]:
    environment = {"HOME": "/tmp", "PATH": "/usr/local/bin:/usr/bin:/bin"}
    environment.update(values)
    return environment


def _rejected(code: str, message: str) -> dict[str, object]:
    return {"status": "rejected", "code": code, "message": message}
