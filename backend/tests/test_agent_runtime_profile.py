from dataclasses import replace
from typing import cast

from _agent_runtime_support import profile

from app.core.agent_runtime import (
    RuntimeMcpServerProfile,
    RuntimeMcpToolPolicy,
    profile_from_payload,
    profile_to_payload,
)
from app.modules.mcp_servers.tool_policy import mcp_schema_hash


def test_runtime_profile_snapshot_keeps_llm_generation_parameters() -> None:
    runtime_profile = replace(
        profile(),
        system_prompt="Always answer with concise headings.",
        capability_relevance_threshold=0.55,
    )

    restored = profile_from_payload(profile_to_payload(runtime_profile))

    assert restored == runtime_profile


def test_runtime_profile_snapshot_keeps_old_payloads_replayable() -> None:
    payload = profile_to_payload(profile())
    llm = cast(dict[str, object], payload["llm"])
    assert isinstance(llm, dict)
    llm.pop("temperature")
    llm.pop("max_tokens")
    llm.pop("thinking_enabled")
    llm.pop("prompt_cache_enabled")
    payload.pop("capability_relevance_threshold")

    restored = profile_from_payload(payload)

    assert restored is not None
    assert restored.llm.temperature == 0.2
    assert restored.llm.max_tokens == 4096
    assert restored.capability_relevance_threshold == 0.4
    assert restored.llm.thinking_enabled is False
    assert restored.llm.prompt_cache_enabled is False


def test_runtime_profile_snapshot_keeps_explicit_thinking_intent() -> None:
    runtime_profile = replace(
        profile(),
        llm=replace(profile().llm, thinking_enabled=True),
    )

    restored = profile_from_payload(profile_to_payload(runtime_profile))

    assert restored == runtime_profile
    assert restored is not None
    assert restored.llm.thinking_enabled is True


def test_runtime_profile_snapshot_keeps_explicit_prompt_cache_intent() -> None:
    runtime_profile = replace(
        profile(),
        llm=replace(profile().llm, prompt_cache_enabled=True),
    )

    restored = profile_from_payload(profile_to_payload(runtime_profile))

    assert restored == runtime_profile
    assert restored is not None
    assert restored.llm.prompt_cache_enabled is True


def test_runtime_profile_snapshot_rejects_invalid_relevance_threshold() -> None:
    payload = profile_to_payload(profile())
    payload["capability_relevance_threshold"] = 1.1

    assert profile_from_payload(payload) is None


def test_runtime_profile_snapshot_never_carries_knowledge_space_authorization() -> None:
    payload = profile_to_payload(replace(profile(), agent_type_key="knowledge"))

    assert "knowledge_space_ids" not in payload
    payload["knowledge_space_ids"] = ["space_stale"]

    restored = profile_from_payload(payload)

    assert restored is not None
    assert restored.agent_type_key == "knowledge"
    assert not hasattr(restored, "knowledge_space_ids")


def test_runtime_profile_snapshot_keeps_server_owned_mcp_policies() -> None:
    schema: dict[str, object] = {"type": "object", "required": ["query"]}
    server = RuntimeMcpServerProfile(
        id="mcp_docs",
        name="Docs",
        transport="streamable_http",
        endpoint="https://mcp.example.test",
        arguments=(),
        encrypted_credentials=(),
        tool_policies=(
            RuntimeMcpToolPolicy(
                name="search",
                description="Search docs",
                input_schema=schema,
                schema_hash=mcp_schema_hash(schema),
                effect="read",
                approval="automatic",
                parallel_safe=True,
            ),
        ),
    )

    restored = profile_from_payload(profile_to_payload(replace(profile(), mcp_servers=(server,))))

    assert restored is not None
    assert restored.mcp_servers == (server,)
