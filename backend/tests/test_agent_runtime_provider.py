from __future__ import annotations

import json
import logging
from dataclasses import replace
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import httpx
import pytest
from _agent_runtime_support import ROOT, credential_cipher, profile

from app.core.config import AppConfig, load_app_config
from app.core.errors import AppError
from app.modules.agent_runtime.contracts import ChatMessage, ModelProviderError, ToolDefinition
from app.modules.agent_runtime.openai_compatible import OpenAiCompatibleModelClient
from app.modules.agent_runtime.tool_schema import JsonSchema as S
from app.modules.agents.repository import AgentBindingRepository
from app.modules.agents.runtime_profile import BoundAgentRuntimeProfileResolver
from app.modules.llm_configs.runtime_catalog import LlmRuntimeCatalog
from app.modules.mcp_servers.runtime_catalog import McpRuntimeCatalog
from app.modules.skills.runtime_catalog import SkillRuntimeCatalog


class _UnreadErrorStream(httpx.AsyncByteStream):
    async def __aiter__(self):
        yield json.dumps(
            {
                "error": {
                    "message": "Thinking mode does not support this tool_choice",
                    "type": "invalid_request_error",
                    "code": "invalid_request_error",
                }
            }
        ).encode()


@pytest.mark.asyncio
async def test_openai_client_decrypts_database_credential_and_keeps_v1_path(
    caplog: pytest.LogCaptureFixture,
) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "done",
                            "reasoning_content": "private analysis",
                        },
                        "finish_reason": "stop",
                    }
                ]
            },
        )

    local_settings = load_app_config(ROOT / "config" / "dev.toml")
    values = local_settings.model_dump(mode="python", by_alias=True)
    values["ai"]["debug_log_prompts"] = False
    settings = AppConfig.model_validate(values)
    client = OpenAiCompatibleModelClient(
        settings, credential_cipher(), transport=httpx.MockTransport(handler)
    )

    with caplog.at_level(logging.INFO, logger="app.modules.agent_runtime.openai_compatible"):
        result = await client.complete(
            profile().llm,
            (ChatMessage(role="user", content="hello"),),
        )

    assert result.content == "done"
    assert result.finish_reason == "stop"
    assert result.reasoning_content == "private analysis"
    assert str(seen[0].url) == "https://api.example.test/v1/chat/completions"
    assert seen[0].headers["authorization"] == "Bearer secret"
    payload = json.loads(seen[0].content)
    assert payload["temperature"] == 0.2
    assert payload["max_tokens"] == settings.ai.agent_max_output_tokens
    assert "thinking" not in payload
    assert "message_count=1" in caplog.text
    assert "output_characters=4" in caplog.text
    assert "hello" not in caplog.text


@pytest.mark.asyncio
async def test_openai_client_streams_sse_deltas() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            content=(
                b'data: {"choices":[{"delta":{"reasoning_content":"private"}}]}\n\n'
                b'data: {"choices":[{"delta":{"content":"Hel"}}]}\n\n'
                b'data: {"choices":[{"delta":{"content":"lo"}}]}\n\n'
                b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
                b"data: [DONE]\n\n"
            ),
        )

    settings = load_app_config(ROOT / "config" / "dev.toml")
    client = OpenAiCompatibleModelClient(
        settings, credential_cipher(), transport=httpx.MockTransport(handler)
    )

    deltas = [
        delta
        async for delta in client.stream(
            profile().llm,
            (ChatMessage(role="user", content="hello"),),
        )
    ]

    assert [item.reasoning_content_delta for item in deltas] == ["private", "", "", ""]
    assert [item.content_delta for item in deltas] == ["", "Hel", "lo", ""]
    assert [item.finish_reason for item in deltas] == [None, None, None, "stop"]
    assert json.loads(seen[0].content)["stream"] is True
    assert "prompt_cache_key" not in json.loads(seen[0].content)
    assert "stream_options" not in json.loads(seen[0].content)


@pytest.mark.asyncio
async def test_openai_client_sends_prompt_cache_key_only_when_enabled() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {"content": "ok"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 5,
                    "total_tokens": 105,
                    "prompt_tokens_details": {"cached_tokens": 80},
                },
            },
        )

    settings = load_app_config(ROOT / "config" / "dev.toml")
    client = OpenAiCompatibleModelClient(
        settings, credential_cipher(), transport=httpx.MockTransport(handler)
    )
    llm = replace(profile().llm, prompt_cache_enabled=True)

    result = await client.complete(llm, (ChatMessage(role="user", content="hello"),))

    payload = json.loads(seen[0].content)
    assert payload["prompt_cache_key"] == f"parrot:llm:{llm.id}"
    assert result.usage is not None
    assert result.usage.prompt_tokens == 100
    assert result.usage.completion_tokens == 5
    assert result.usage.total_tokens == 105
    assert result.usage.cached_tokens == 80


@pytest.mark.asyncio
async def test_openai_client_streams_usage_when_prompt_cache_enabled() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            content=(
                b'data: {"choices":[{"delta":{"content":"Hi"}}]}\n\n'
                b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
                b'data: {"choices":[],"usage":{"prompt_tokens":12,"completion_tokens":1,'
                b'"total_tokens":13,"prompt_tokens_details":{"cached_tokens":10}}}\n\n'
                b"data: [DONE]\n\n"
            ),
        )

    settings = load_app_config(ROOT / "config" / "dev.toml")
    client = OpenAiCompatibleModelClient(
        settings, credential_cipher(), transport=httpx.MockTransport(handler)
    )

    deltas = [
        delta
        async for delta in client.stream(
            replace(profile().llm, prompt_cache_enabled=True),
            (ChatMessage(role="user", content="hello"),),
        )
    ]

    payload = json.loads(seen[0].content)
    assert payload["prompt_cache_key"] == "parrot:llm:llm_test"
    assert payload["stream_options"] == {"include_usage": True}
    assert deltas[0].content_delta == "Hi"
    assert deltas[-1].usage is not None
    assert deltas[-1].usage.cached_tokens == 10
    assert deltas[-1].usage.prompt_tokens == 12


@pytest.mark.asyncio
async def test_openai_client_sends_required_tool_choice_without_provider_branching() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=b"data: [DONE]\n\n")

    settings = load_app_config(ROOT / "config" / "dev.toml")
    client = OpenAiCompatibleModelClient(
        settings, credential_cipher(), transport=httpx.MockTransport(handler)
    )
    tool = ToolDefinition(
        name="ask_user",
        description="Ask the user for missing information.",
        parameters=S.object(),
    )

    _ = [
        delta
        async for delta in client.stream(
            replace(profile().llm, provider="custom-vendor"),
            (ChatMessage(role="user", content="hello"),),
            (tool,),
            tool_choice="required",
        )
    ]

    payload = json.loads(seen[0].content)
    assert payload["tool_choice"] == "required"
    assert payload["tools"][0]["function"]["name"] == "ask_user"


@pytest.mark.asyncio
async def test_openai_client_classifies_a_rejected_tool_choice() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "error": {
                    "message": "Thinking mode does not support this tool_choice",
                    "type": "invalid_request_error",
                    "code": "invalid_request_error",
                }
            },
        )

    settings = load_app_config(ROOT / "config" / "dev.toml")
    client = OpenAiCompatibleModelClient(
        settings, credential_cipher(), transport=httpx.MockTransport(handler)
    )
    tool = ToolDefinition(
        name="ask_user",
        description="Ask the user for missing information.",
        parameters=S.object(),
    )

    with pytest.raises(ModelProviderError) as error:
        _ = [
            delta
            async for delta in client.stream(
                profile().llm,
                (ChatMessage(role="user", content="hello"),),
                (tool,),
                tool_choice="required",
            )
        ]

    assert error.value.tool_choice_rejected is True


@pytest.mark.asyncio
async def test_openai_client_reads_streaming_error_before_classifying_it() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, stream=_UnreadErrorStream())

    settings = load_app_config(ROOT / "config" / "dev.toml")
    client = OpenAiCompatibleModelClient(
        settings, credential_cipher(), transport=httpx.MockTransport(handler)
    )
    tool = ToolDefinition(
        name="ask_user",
        description="Ask the user for missing information.",
        parameters=S.object(),
    )

    with pytest.raises(ModelProviderError) as error:
        _ = [
            delta
            async for delta in client.stream(
                profile().llm,
                (ChatMessage(role="user", content="hello"),),
                (tool,),
                tool_choice="required",
            )
        ]

    assert error.value.tool_choice_rejected is True


@pytest.mark.asyncio
async def test_openai_client_preserves_private_reasoning_on_a_tool_turn() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "done"}}]})

    settings = load_app_config(ROOT / "config" / "dev.toml")
    client = OpenAiCompatibleModelClient(
        settings, credential_cipher(), transport=httpx.MockTransport(handler)
    )

    await client.complete(
        profile().llm,
        (
            ChatMessage(
                role="assistant",
                content=None,
                reasoning_content="private analysis",
            ),
        ),
    )

    message = json.loads(seen[0].content)["messages"][0]
    assert message["reasoning_content"] == "private analysis"


@pytest.mark.asyncio
async def test_openai_client_logs_the_provider_ready_prompt_only_when_enabled(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "done"}}]})

    settings = load_app_config(ROOT / "config" / "dev.toml")
    values = settings.model_dump(mode="python", by_alias=True)
    values["ai"]["debug_log_prompts"] = True
    client = OpenAiCompatibleModelClient(
        AppConfig.model_validate(values),
        credential_cipher(),
        transport=httpx.MockTransport(handler),
    )

    with caplog.at_level(logging.WARNING, logger="app.modules.agent_runtime.openai_compatible"):
        await client.complete(
            profile().llm,
            (
                ChatMessage(role="system", content="Private instruction"),
                ChatMessage(role="user", content="Show the raw prompt"),
            ),
        )

    assert "LLM raw prompt dispatched" in caplog.text
    assert '"role": "system"' in caplog.text
    assert "Private instruction" in caplog.text
    assert "Show the raw prompt" in caplog.text
    assert "Bearer secret" not in caplog.text


@pytest.mark.asyncio
async def test_provider_label_does_not_change_the_openai_compatible_request() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "done"}}]})

    settings = load_app_config(ROOT / "config" / "dev.toml")
    client = OpenAiCompatibleModelClient(
        settings, credential_cipher(), transport=httpx.MockTransport(handler)
    )
    llm = replace(
        profile().llm,
        provider="custom-vendor",
        temperature=0.7,
        max_tokens=settings.ai.agent_max_output_tokens + 1,
    )

    await client.complete(llm, (ChatMessage(role="user", content="hello"),))

    payload = json.loads(seen[0].content)
    assert payload["temperature"] == 0.7
    assert payload["max_tokens"] == settings.ai.agent_max_output_tokens
    assert "thinking" not in payload


@pytest.mark.asyncio
async def test_profile_resolver_uses_only_the_agents_bound_capabilities() -> None:
    bound_llm = profile().llm
    bound_skills = profile().skills
    system_prompt = "Answer with verified, concise results."
    bindings = SimpleNamespace(
        get_system_prompt=AsyncMock(return_value=system_prompt),
        get_capability_relevance_threshold=AsyncMock(return_value=0.55),
        get_llm_bindings=AsyncMock(return_value=((bound_llm.id,), bound_llm.id)),
        get_skill_bindings=AsyncMock(return_value=(bound_skills[0].id,)),
        get_mcp_server_bindings=AsyncMock(return_value=()),
    )
    llms = SimpleNamespace(get_active=AsyncMock(return_value=bound_llm))
    skills = SimpleNamespace(get_published=AsyncMock(return_value=bound_skills))
    mcp_servers = SimpleNamespace(get_active=AsyncMock(return_value=()))
    resolver = BoundAgentRuntimeProfileResolver(
        cast(AgentBindingRepository, bindings),
        cast(LlmRuntimeCatalog, llms),
        cast(SkillRuntimeCatalog, skills),
        cast(McpRuntimeCatalog, mcp_servers),
    )

    resolved = await resolver.resolve("tenant_test", "agent_test")

    assert resolved == replace(
        profile(),
        system_prompt=system_prompt,
        capability_relevance_threshold=0.55,
    )
    llms.get_active.assert_awaited_once_with("tenant_test", bound_llm.id)
    skills.get_published.assert_awaited_once_with("tenant_test", (bound_skills[0].id,))


@pytest.mark.asyncio
async def test_profile_resolver_fails_closed_when_default_llm_is_missing() -> None:
    bindings = SimpleNamespace(
        get_system_prompt=AsyncMock(return_value=""),
        get_llm_bindings=AsyncMock(return_value=((), None)),
    )
    resolver = BoundAgentRuntimeProfileResolver(
        cast(AgentBindingRepository, bindings),
        cast(LlmRuntimeCatalog, SimpleNamespace()),
        cast(SkillRuntimeCatalog, SimpleNamespace()),
        cast(McpRuntimeCatalog, SimpleNamespace()),
    )

    with pytest.raises(AppError, match="runtime configuration") as error:
        await resolver.resolve("tenant_test", "agent_test")

    assert error.value.code == "AI_RUNTIME_CONFIGURATION_INVALID"
