from collections.abc import AsyncIterator

from app.core.agent_runtime import RuntimeLlmProfile
from app.core.config import AppConfig
from app.infrastructure.credential_cipher import CredentialCipher
from app.modules.agent_runtime.contracts import (
    AgentModelPort,
    ChatCompletion,
    ChatCompletionDelta,
    ChatMessage,
    ModelProviderError,
    ModelToolChoice,
    ToolDefinition,
)
from app.modules.agent_runtime.openai_compatible import OpenAiCompatibleModelClient
from app.modules.model_providers.catalog import provider_capability


class ProviderLlmClient(AgentModelPort):
    """Provider-aware LLM facade used by runtime and management probes."""

    def __init__(
        self,
        settings: AppConfig,
        cipher: CredentialCipher,
        *,
        timeout_seconds: float | None = None,
    ) -> None:
        self._openai_chat = OpenAiCompatibleModelClient(
            settings, cipher, timeout_seconds=timeout_seconds
        )

    def validate(self, llm: RuntimeLlmProfile) -> None:
        self._adapter(llm)
        self._openai_chat.validate(llm)

    async def complete(
        self,
        llm: RuntimeLlmProfile,
        messages: tuple[ChatMessage, ...],
        tools: tuple[ToolDefinition, ...] = (),
        *,
        tool_choice: ModelToolChoice | None = None,
    ) -> ChatCompletion:
        self._adapter(llm)
        return await self._openai_chat.complete(llm, messages, tools, tool_choice=tool_choice)

    def stream(
        self,
        llm: RuntimeLlmProfile,
        messages: tuple[ChatMessage, ...],
        tools: tuple[ToolDefinition, ...] = (),
        *,
        tool_choice: ModelToolChoice | None = None,
    ) -> AsyncIterator[ChatCompletionDelta]:
        self._adapter(llm)
        return self._openai_chat.stream(llm, messages, tools, tool_choice=tool_choice)

    @staticmethod
    def _adapter(llm: RuntimeLlmProfile) -> None:
        capability = provider_capability(llm.provider, "llm", allow_legacy_llm=True)
        if capability.adapter != "openai_chat":
            raise ModelProviderError("Configured LLM provider adapter is unavailable")
