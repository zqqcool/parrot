from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import cast

import httpx

from app.core.agent_runtime import RuntimeLlmProfile
from app.core.config import AppConfig
from app.core.errors import AppError
from app.infrastructure.credential_cipher import (
    CredentialCipher,
    CredentialCipherError,
    llm_credential_context,
)
from app.modules.agent_runtime.contracts import (
    AgentModelPort,
    ChatCompletion,
    ChatCompletionDelta,
    ChatMessage,
    ModelProviderError,
    ModelTokenUsage,
    ModelToolChoice,
    ToolCall,
    ToolCallDelta,
    ToolDefinition,
)
from app.modules.agent_runtime.provider_request import message_payload, tool_definition_payload
from app.modules.model_providers.catalog import provider_capability

logger = logging.getLogger(__name__)


class OpenAiCompatibleModelClient(AgentModelPort):
    def __init__(
        self,
        settings: AppConfig,
        cipher: CredentialCipher,
        *,
        timeout_seconds: float | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._cipher = cipher
        self._allowed_hosts = frozenset(host.casefold() for host in settings.ai.allowed_model_hosts)
        self._require_https = settings.app.environment == "prod"
        self._timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else settings.runtime.request_timeout_seconds
        )
        self._max_output_tokens = settings.ai.agent_max_output_tokens
        self._debug_log_prompts = settings.ai.debug_log_prompts
        self._transport = transport

    async def complete(
        self,
        llm: RuntimeLlmProfile,
        messages: tuple[ChatMessage, ...],
        tools: tuple[ToolDefinition, ...] = (),
        *,
        tool_choice: ModelToolChoice | None = None,
    ) -> ChatCompletion:
        url = self._completion_url(llm)
        payload = self._payload(llm, messages, tools, tool_choice=tool_choice)
        self._log_raw_prompt(llm, payload)
        logger.info(
            "LLM request dispatched llm_id=%s provider=%s model=%s message_count=%s "
            "message_characters=%s tool_count=%s",
            llm.id,
            llm.provider,
            llm.model,
            len(messages),
            sum(len(message.content or "") for message in messages),
            len(tools),
        )
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds, transport=self._transport
            ) as client:
                response = await client.post(
                    url,
                    headers={"Authorization": f"Bearer {self._credential(llm)}"},
                    json=payload,
                )
                response.raise_for_status()
                raw = cast(object, response.json())
        except httpx.HTTPStatusError as exc:
            retryable = exc.response.status_code in {408, 409, 429, 500, 502, 503, 504}
            raise ModelProviderError(
                "Model provider request failed",
                retryable=retryable,
                tool_choice_rejected=_tool_choice_rejected(exc.response, tool_choice),
            ) from exc
        except httpx.RequestError as exc:
            raise ModelProviderError("Model provider request failed", retryable=True) from exc
        except ValueError as exc:
            raise ModelProviderError("Model provider response is invalid") from exc
        completion = _completion_from_response(raw)
        logger.info(
            "LLM response received llm_id=%s provider=%s model=%s output_characters=%s "
            "tool_call_count=%s",
            llm.id,
            llm.provider,
            llm.model,
            len(completion.content or ""),
            len(completion.tool_calls),
        )
        return completion

    async def stream(
        self,
        llm: RuntimeLlmProfile,
        messages: tuple[ChatMessage, ...],
        tools: tuple[ToolDefinition, ...] = (),
        *,
        tool_choice: ModelToolChoice | None = None,
    ) -> AsyncIterator[ChatCompletionDelta]:
        url = self._completion_url(llm)
        payload = self._payload(llm, messages, tools, tool_choice=tool_choice)
        payload["stream"] = True
        if llm.prompt_cache_enabled:
            payload["stream_options"] = {"include_usage": True}
        self._log_raw_prompt(llm, payload)
        logger.info(
            "LLM stream dispatched llm_id=%s provider=%s model=%s message_count=%s "
            "message_characters=%s tool_count=%s",
            llm.id,
            llm.provider,
            llm.model,
            len(messages),
            sum(len(message.content or "") for message in messages),
            len(tools),
        )
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds, transport=self._transport
            ) as client:
                async with client.stream(
                    "POST",
                    url,
                    headers={"Authorization": f"Bearer {self._credential(llm)}"},
                    json=payload,
                ) as response:
                    if response.is_error:
                        await response.aread()
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line.removeprefix("data:").strip()
                        if data == "[DONE]":
                            return
                        try:
                            raw = cast(object, json.loads(data))
                        except json.JSONDecodeError as exc:
                            raise ModelProviderError("Model provider stream is invalid") from exc
                        delta = _stream_delta(raw)
                        if (
                            delta.content_delta
                            or delta.reasoning_content_delta
                            or delta.tool_call_deltas
                            or delta.finish_reason is not None
                            or delta.usage is not None
                        ):
                            yield delta
        except httpx.HTTPStatusError as exc:
            retryable = exc.response.status_code in {408, 409, 429, 500, 502, 503, 504}
            raise ModelProviderError(
                "Model provider stream failed",
                retryable=retryable,
                tool_choice_rejected=_tool_choice_rejected(exc.response, tool_choice),
            ) from exc
        except httpx.RequestError as exc:
            raise ModelProviderError("Model provider stream failed", retryable=True) from exc

    def _payload(
        self,
        llm: RuntimeLlmProfile,
        messages: tuple[ChatMessage, ...],
        tools: tuple[ToolDefinition, ...],
        *,
        tool_choice: ModelToolChoice | None,
    ) -> dict[str, object]:
        if tool_choice == "required" and not tools:
            raise ModelProviderError("Required tool choice needs at least one tool")
        payload: dict[str, object] = {
            "model": llm.model,
            "messages": [message_payload(item) for item in messages],
            "temperature": llm.temperature,
            "max_tokens": min(llm.max_tokens, self._max_output_tokens),
        }
        if tools:
            payload["tools"] = [tool_definition_payload(item) for item in tools]
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice
        if llm.prompt_cache_enabled:
            payload["prompt_cache_key"] = f"parrot:llm:{llm.id}"
        return payload

    def validate(self, llm: RuntimeLlmProfile) -> None:
        self._completion_url(llm)
        self._credential(llm)

    def _completion_url(self, llm: RuntimeLlmProfile) -> str:
        if not llm.base_url:
            raise ModelProviderError("Configured model endpoint is missing")
        try:
            base_url = httpx.URL(llm.base_url)
        except ValueError as exc:
            raise ModelProviderError("Configured model endpoint is invalid") from exc
        if (
            base_url.scheme not in {"http", "https"}
            or not base_url.host
            or base_url.query
            or base_url.fragment
            or base_url.username
            or base_url.password
        ):
            raise ModelProviderError("Configured model endpoint is invalid")
        if self._require_https and base_url.scheme != "https":
            raise ModelProviderError("Production model endpoint must use HTTPS")
        try:
            capability = provider_capability(llm.provider, "llm", allow_legacy_llm=True)
        except AppError as error:
            raise ModelProviderError("Configured model provider is unavailable") from error
        host = base_url.host.casefold()
        provider_trusted = host in {item.casefold() for item in capability.trusted_hosts} or any(
            host.endswith(suffix.casefold()) for suffix in capability.trusted_host_suffixes
        )
        if self._allowed_hosts and host not in self._allowed_hosts and not provider_trusted:
            raise ModelProviderError("Configured model endpoint is not allowlisted")
        return f"{str(base_url).rstrip('/')}/chat/completions"

    def _credential(self, llm: RuntimeLlmProfile) -> str:
        if not llm.credential_envelope:
            raise ModelProviderError("Configured model credential is missing")
        try:
            return self._cipher.decrypt(
                llm.credential_envelope, context=llm_credential_context(llm.id)
            )
        except CredentialCipherError as error:
            raise ModelProviderError("Configured model credential is unavailable") from error

    def _log_raw_prompt(self, llm: RuntimeLlmProfile, payload: dict[str, object]) -> None:
        """Emit the provider-ready prompt only for explicitly enabled local diagnostics."""
        if not self._debug_log_prompts:
            return
        logger.warning(
            "LLM raw prompt dispatched llm_id=%s provider=%s model=%s payload=\n%s",
            llm.id,
            llm.provider,
            llm.model,
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        )


def _tool_choice_rejected(
    response: httpx.Response,
    tool_choice: ModelToolChoice | None,
) -> bool:
    if tool_choice is None or response.status_code not in {400, 422}:
        return False
    try:
        raw = cast(object, response.json())
    except ValueError:
        return False
    if not isinstance(raw, dict):
        return False
    error = cast(dict[str, object], raw).get("error")
    if not isinstance(error, dict):
        return False
    values = cast(dict[str, object], error)
    parameter = values.get("param")
    message = values.get("message")
    return parameter == "tool_choice" or (
        isinstance(message, str) and "tool_choice" in message.casefold()
    )


def _completion_from_response(raw: object) -> ChatCompletion:
    if not isinstance(raw, dict):
        raise ModelProviderError("Model provider response is invalid")
    response = cast(dict[str, object], raw)
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise ModelProviderError("Model provider response is invalid")
    choice = cast(dict[str, object], choices[0])
    message = choice.get("message")
    if not isinstance(message, dict):
        raise ModelProviderError("Model provider response is invalid")
    typed_message = cast(dict[str, object], message)
    content = typed_message.get("content")
    reasoning_content = typed_message.get("reasoning_content")
    tool_calls = typed_message.get("tool_calls")
    if reasoning_content is not None and not isinstance(reasoning_content, str):
        raise ModelProviderError("Model provider reasoning content is invalid")
    return ChatCompletion(
        content=content if isinstance(content, str) else None,
        tool_calls=_tool_calls(tool_calls),
        finish_reason=_finish_reason(choice.get("finish_reason")),
        reasoning_content=reasoning_content,
        usage=_usage_from_response(response),
    )


def _stream_delta(raw: object) -> ChatCompletionDelta:
    if not isinstance(raw, dict):
        raise ModelProviderError("Model provider stream is invalid")
    response = cast(dict[str, object], raw)
    usage = _usage_from_response(response)
    choices = response.get("choices")
    if not isinstance(choices, list):
        raise ModelProviderError("Model provider stream is invalid")
    if not choices:
        if usage is None:
            raise ModelProviderError("Model provider stream is invalid")
        return ChatCompletionDelta(usage=usage)
    choice_raw = cast(list[object], choices)[0]
    if not isinstance(choice_raw, dict):
        raise ModelProviderError("Model provider stream is invalid")
    choice = cast(dict[str, object], choice_raw)
    delta_raw = choice.get("delta")
    if not isinstance(delta_raw, dict):
        raise ModelProviderError("Model provider stream is invalid")
    delta = cast(dict[str, object], delta_raw)
    content = delta.get("content")
    reasoning_content = delta.get("reasoning_content")
    finish_reason = _finish_reason(choice.get("finish_reason"))
    calls = _stream_tool_calls(delta.get("tool_calls"))
    if content is not None and not isinstance(content, str):
        raise ModelProviderError("Model provider stream is invalid")
    if reasoning_content is not None and not isinstance(reasoning_content, str):
        raise ModelProviderError("Model provider stream reasoning content is invalid")
    return ChatCompletionDelta(
        content_delta=content or "",
        tool_call_deltas=calls,
        finish_reason=finish_reason,
        reasoning_content_delta=reasoning_content or "",
        usage=usage,
    )


def _stream_tool_calls(raw: object) -> tuple[ToolCallDelta, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ModelProviderError("Model provider stream is invalid")
    return tuple(_tool_call_delta(item) for item in cast(list[object], raw))


def _usage_from_response(response: dict[str, object]) -> ModelTokenUsage | None:
    raw = response.get("usage")
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ModelProviderError("Model provider usage is invalid")
    values = cast(dict[str, object], raw)
    cached = values.get("cached_tokens")
    details = values.get("prompt_tokens_details")
    if isinstance(details, dict):
        detail_cached = cast(dict[str, object], details).get("cached_tokens")
        if detail_cached is not None:
            cached = detail_cached
    prompt_tokens = _optional_token_count(values.get("prompt_tokens"))
    completion_tokens = _optional_token_count(values.get("completion_tokens"))
    total_tokens = _optional_token_count(values.get("total_tokens"))
    cached_tokens = _optional_token_count(cached)
    if (
        prompt_tokens is None
        and completion_tokens is None
        and total_tokens is None
        and cached_tokens is None
    ):
        return None
    return ModelTokenUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        cached_tokens=cached_tokens,
    )


def _optional_token_count(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ModelProviderError("Model provider usage is invalid")
    return value


def _finish_reason(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ModelProviderError("Model provider finish reason is invalid")
    return value


def _tool_call_delta(raw: object) -> ToolCallDelta:
    if not isinstance(raw, dict):
        raise ModelProviderError("Model provider stream is invalid")
    item = cast(dict[str, object], raw)
    index = item.get("index")
    if not isinstance(index, int):
        raise ModelProviderError("Model provider stream is invalid")
    function_raw = item.get("function")
    if function_raw is not None and not isinstance(function_raw, dict):
        raise ModelProviderError("Model provider stream is invalid")
    function = cast(dict[str, object], function_raw) if isinstance(function_raw, dict) else None
    name = function.get("name") if function is not None else None
    arguments = function.get("arguments") if function is not None else None
    call_id = item.get("id")
    if call_id is not None and not isinstance(call_id, str):
        raise ModelProviderError("Model provider stream is invalid")
    if name is not None and not isinstance(name, str):
        raise ModelProviderError("Model provider stream is invalid")
    if arguments is not None and not isinstance(arguments, str):
        raise ModelProviderError("Model provider stream is invalid")
    return ToolCallDelta(
        index=index,
        id=call_id,
        name=name,
        arguments_delta=arguments or "",
    )


def _tool_calls(value: object) -> tuple[ToolCall, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ModelProviderError("Model provider response is invalid")
    calls: list[ToolCall] = []
    for raw_item in cast(list[object], value):
        item = cast(dict[str, object], raw_item) if isinstance(raw_item, dict) else None
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise ModelProviderError("Model provider response is invalid")
        function = item.get("function")
        if not isinstance(function, dict):
            raise ModelProviderError("Model provider response is invalid")
        typed_function = cast(dict[str, object], function)
        if not isinstance(typed_function.get("name"), str):
            raise ModelProviderError("Model provider response is invalid")
        arguments = _arguments(typed_function.get("arguments"))
        calls.append(
            ToolCall(
                id=cast(str, item["id"]),
                name=cast(str, typed_function["name"]),
                arguments=arguments,
            )
        )
    return tuple(calls)


def _arguments(value: object) -> dict[str, object]:
    if not isinstance(value, str):
        raise ModelProviderError("Model provider response is invalid")
    try:
        result = cast(object, json.loads(value))
    except json.JSONDecodeError as exc:
        raise ModelProviderError("Model provider response is invalid") from exc
    if not isinstance(result, dict):
        raise ModelProviderError("Model provider response is invalid")
    return cast(dict[str, object], result)
