from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, cast

from app.core.agent_types import AgentTypeKey, agent_type_policy

DEFAULT_CAPABILITY_RELEVANCE_THRESHOLD = 0.4


@dataclass(frozen=True)
class RuntimeLlmProfile:
    id: str
    provider: str
    model: str
    base_url: str | None
    credential_envelope: str | None
    temperature: float = 0.2
    max_tokens: int = 4096
    thinking_enabled: bool = False
    prompt_cache_enabled: bool = False


@dataclass(frozen=True)
class RuntimeSkillProfile:
    id: str
    name: str
    description: str
    instructions: str
    manifest: dict[str, object]
    version: int
    package_path: str | None = None
    package_sha256: str | None = None

    @property
    def requires_mcp(self) -> bool:
        return False

    @property
    def is_executable(self) -> bool:
        if self.manifest.get("execute") is True:
            return isinstance(self.manifest.get("entrypoint"), str)
        runtime = self.manifest.get("runtime")
        return isinstance(runtime, dict) and isinstance(
            cast(dict[str, object], runtime).get("entrypoint"), str
        )

    @property
    def is_instruction_only(self) -> bool:
        return not self.is_executable and not self.requires_mcp


@dataclass(frozen=True)
class RuntimeMcpToolPolicy:
    name: str
    description: str
    input_schema: dict[str, object]
    schema_hash: str
    effect: str
    approval: str
    parallel_safe: bool = False


@dataclass(frozen=True)
class RuntimeMcpServerProfile:
    id: str
    name: str
    transport: str
    endpoint: str
    arguments: tuple[str, ...]
    encrypted_credentials: tuple[dict[str, str], ...]
    tool_policies: tuple[RuntimeMcpToolPolicy, ...] = ()

    @property
    def is_local_process(self) -> bool:
        return self.transport == "stdio"


@dataclass(frozen=True)
class AgentRuntimeProfile:
    llm: RuntimeLlmProfile
    skills: tuple[RuntimeSkillProfile, ...]
    system_prompt: str = ""
    mcp_servers: tuple[RuntimeMcpServerProfile, ...] = ()
    agent_type_key: str = AgentTypeKey.FUNCTIONAL
    capability_relevance_threshold: float = DEFAULT_CAPABILITY_RELEVANCE_THRESHOLD

    @property
    def is_knowledge_only(self) -> bool:
        policy = agent_type_policy(self.agent_type_key)
        return policy.uses_knowledge if policy is not None else False

    @property
    def allows_runtime_tools(self) -> bool:
        policy = agent_type_policy(self.agent_type_key)
        return policy.allows_runtime_tools if policy is not None else False

    @property
    def uses_functional_planner(self) -> bool:
        policy = agent_type_policy(self.agent_type_key)
        return policy.uses_functional_planner if policy is not None else False


class AgentRuntimeProfileResolver(Protocol):
    async def resolve(self, tenant_id: str, agent_id: str) -> AgentRuntimeProfile: ...


def profile_to_payload(profile: AgentRuntimeProfile) -> dict[str, object]:
    """Serialize a replay-safe profile without including resolved credentials."""
    return {
        "llm": {
            "id": profile.llm.id,
            "provider": profile.llm.provider,
            "model": profile.llm.model,
            "base_url": profile.llm.base_url,
            "credential_envelope": profile.llm.credential_envelope,
            "temperature": profile.llm.temperature,
            "max_tokens": profile.llm.max_tokens,
            "thinking_enabled": profile.llm.thinking_enabled,
            "prompt_cache_enabled": profile.llm.prompt_cache_enabled,
        },
        "skills": [
            {
                "id": skill.id,
                "name": skill.name,
                "description": skill.description,
                "instructions": skill.instructions,
                "manifest": skill.manifest,
                "version": skill.version,
                "package_path": skill.package_path,
                "package_sha256": skill.package_sha256,
            }
            for skill in profile.skills
        ],
        "system_prompt": profile.system_prompt,
        "agent_type_key": profile.agent_type_key,
        "capability_relevance_threshold": profile.capability_relevance_threshold,
        "mcp_servers": [
            {
                "id": server.id,
                "name": server.name,
                "transport": server.transport,
                "endpoint": server.endpoint,
                "arguments": list(server.arguments),
                "encrypted_credentials": list(server.encrypted_credentials),
                "tool_policies": [
                    {
                        "name": policy.name,
                        "description": policy.description,
                        "input_schema": policy.input_schema,
                        "schema_hash": policy.schema_hash,
                        "effect": policy.effect,
                        "approval": policy.approval,
                        "parallel_safe": policy.parallel_safe,
                    }
                    for policy in server.tool_policies
                ],
            }
            for server in profile.mcp_servers
        ],
    }


def profile_from_payload(value: object) -> AgentRuntimeProfile | None:
    if not isinstance(value, dict):
        return None
    payload = cast(dict[str, object], value)
    llm = payload.get("llm")
    skills = payload.get("skills")
    mcp_servers = payload.get("mcp_servers", [])
    system_prompt = payload.get("system_prompt", "")
    agent_type_key = payload.get("agent_type_key", AgentTypeKey.FUNCTIONAL)
    relevance_threshold = payload.get(
        "capability_relevance_threshold", DEFAULT_CAPABILITY_RELEVANCE_THRESHOLD
    )
    if (
        not isinstance(llm, dict)
        or not isinstance(skills, list)
        or not isinstance(mcp_servers, list)
        or not isinstance(system_prompt, str)
        or not isinstance(agent_type_key, str)
        or isinstance(relevance_threshold, bool)
        or not isinstance(relevance_threshold, int | float)
        or not 0 <= float(relevance_threshold) <= 1
        or len(system_prompt) > 20_000
        or len(agent_type_key) > 32
    ):
        return None
    llm_profile = _llm_from_payload(cast(dict[str, object], llm))
    skill_values = cast(list[object], skills)
    skill_profiles = tuple(
        item for item in (_skill_from_payload(raw) for raw in skill_values) if item is not None
    )
    server_values = cast(list[object], mcp_servers)
    server_profiles = tuple(
        item
        for item in (_mcp_server_from_payload(raw) for raw in server_values)
        if item is not None
    )
    if (
        llm_profile is None
        or len(skill_profiles) != len(skill_values)
        or len(server_profiles) != len(server_values)
    ):
        return None
    return AgentRuntimeProfile(
        llm=llm_profile,
        skills=skill_profiles,
        system_prompt=system_prompt,
        mcp_servers=server_profiles,
        agent_type_key=agent_type_key,
        capability_relevance_threshold=float(relevance_threshold),
    )


def _llm_from_payload(value: dict[str, Any]) -> RuntimeLlmProfile | None:
    fields = ("id", "provider", "model")
    if any(not isinstance(value.get(field), str) or not value[field] for field in fields):
        return None
    base_url = value.get("base_url")
    credential_envelope = value.get("credential_envelope")
    temperature = value.get("temperature", 0.2)
    max_tokens = value.get("max_tokens", 4096)
    thinking_enabled = value.get("thinking_enabled", False)
    prompt_cache_enabled = value.get("prompt_cache_enabled", False)
    if base_url is not None and not isinstance(base_url, str):
        return None
    if credential_envelope is not None and not isinstance(credential_envelope, str):
        return None
    if (
        isinstance(temperature, bool)
        or not isinstance(temperature, (int, float))
        or not 0 <= float(temperature) <= 2
        or isinstance(max_tokens, bool)
        or not isinstance(max_tokens, int)
        or not 1 <= max_tokens <= 32768
        or not isinstance(thinking_enabled, bool)
        or not isinstance(prompt_cache_enabled, bool)
    ):
        return None
    return RuntimeLlmProfile(
        id=value["id"],
        provider=value["provider"],
        model=value["model"],
        base_url=base_url,
        credential_envelope=credential_envelope,
        temperature=float(temperature),
        max_tokens=max_tokens,
        thinking_enabled=thinking_enabled,
        prompt_cache_enabled=prompt_cache_enabled,
    )


def _skill_from_payload(value: object) -> RuntimeSkillProfile | None:
    if not isinstance(value, dict):
        return None
    payload = cast(dict[str, object], value)
    fields = ("id", "name", "description", "instructions")
    if any(not isinstance(payload.get(field), str) for field in fields):
        return None
    manifest = payload.get("manifest")
    version = payload.get("version")
    package_path = payload.get("package_path")
    package_sha256 = payload.get("package_sha256")
    if (
        not isinstance(manifest, dict)
        or not isinstance(version, int)
        or (package_path is not None and not isinstance(package_path, str))
        or (package_sha256 is not None and not isinstance(package_sha256, str))
    ):
        return None
    return RuntimeSkillProfile(
        id=cast(str, payload["id"]),
        name=cast(str, payload["name"]),
        description=cast(str, payload["description"]),
        instructions=cast(str, payload["instructions"]),
        manifest=cast(dict[str, object], manifest),
        version=version,
        package_path=package_path,
        package_sha256=package_sha256,
    )


def _mcp_server_from_payload(value: object) -> RuntimeMcpServerProfile | None:
    if not isinstance(value, dict):
        return None
    payload = cast(dict[str, object], value)
    fields = ("id", "name", "transport", "endpoint")
    if any(not isinstance(payload.get(field), str) or not payload[field] for field in fields):
        return None
    arguments = payload.get("arguments")
    encrypted_credentials = payload.get("encrypted_credentials")
    tool_policies = payload.get("tool_policies", [])
    typed_arguments = cast(list[object], arguments) if isinstance(arguments, list) else None
    typed_credentials = _mcp_encrypted_credentials(encrypted_credentials)
    typed_policies = _mcp_tool_policies(tool_policies)
    if (
        typed_arguments is None
        or not all(isinstance(item, str) for item in typed_arguments)
        or typed_credentials is None
        or typed_policies is None
    ):
        return None
    return RuntimeMcpServerProfile(
        id=cast(str, payload["id"]),
        name=cast(str, payload["name"]),
        transport=cast(str, payload["transport"]),
        endpoint=cast(str, payload["endpoint"]),
        arguments=tuple(cast(str, item) for item in typed_arguments),
        encrypted_credentials=typed_credentials,
        tool_policies=typed_policies,
    )


def _mcp_tool_policies(value: object) -> tuple[RuntimeMcpToolPolicy, ...] | None:
    if not isinstance(value, list):
        return None
    policies: list[RuntimeMcpToolPolicy] = []
    for raw in cast(list[object], value):
        if not isinstance(raw, dict):
            return None
        item = cast(dict[str, object], raw)
        if not all(
            isinstance(item.get(key), str)
            for key in ("name", "description", "schema_hash", "effect", "approval")
        ) or not isinstance(item.get("input_schema"), dict):
            return None
        parallel_safe = item.get("parallel_safe", False)
        if not isinstance(parallel_safe, bool):
            return None
        policies.append(
            RuntimeMcpToolPolicy(
                name=cast(str, item["name"]),
                description=cast(str, item["description"]),
                input_schema=cast(dict[str, object], item["input_schema"]),
                schema_hash=cast(str, item["schema_hash"]),
                effect=cast(str, item["effect"]),
                approval=cast(str, item["approval"]),
                parallel_safe=parallel_safe,
            )
        )
    return tuple(policies)


def _mcp_encrypted_credentials(value: object) -> tuple[dict[str, str], ...] | None:
    if not isinstance(value, list):
        return None
    credentials: list[dict[str, str]] = []
    for raw in cast(list[object], value):
        if not isinstance(raw, dict):
            return None
        item = cast(dict[object, object], raw)
        if not all(
            isinstance(key, str) and isinstance(item_value, str) for key, item_value in item.items()
        ):
            return None
        typed_item = cast(dict[str, str], item)
        if set(typed_item) != {"target", "name", "envelope"}:
            return None
        credentials.append(typed_item)
    return tuple(credentials)
