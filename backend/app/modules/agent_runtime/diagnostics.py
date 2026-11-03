from __future__ import annotations

import logging
from time import monotonic
from typing import cast

from app.core.agent_runtime import RuntimeLlmProfile
from app.modules.agent_runtime.contracts import (
    ChatCompletion,
    ChatMessage,
    ModelToolChoice,
    ToolCall,
    ToolDefinition,
)
from app.modules.agent_runtime.observations import ToolObservation
from app.modules.agent_runtime.provider_request import provider_request_snapshot
from app.modules.interactions.runtime import RuntimeEventSink, RuntimeRequest

logger = logging.getLogger(__name__)


class RuntimeDiagnostics:
    """Persists management-only runtime diagnostics without public event publication.

    Raw model request and response snapshots are an explicit dev/SIT debugging exception.
    The runtime factory enables them only through ``ai.debug_capture_prompts``;
    prod configuration is rejected before the worker starts.
    """

    def __init__(
        self,
        request: RuntimeRequest,
        events: RuntimeEventSink,
        *,
        capture_prompts: bool = False,
    ) -> None:
        self._request = request
        self._events = events
        self._capture_prompts = capture_prompts
        self._started_at = monotonic()
        self._model_turn = 0

    async def model_request(
        self,
        phase: str,
        llm: RuntimeLlmProfile,
        messages: tuple[ChatMessage, ...],
        tools: tuple[ToolDefinition, ...],
        attempt: int,
        tool_choice: ModelToolChoice | None = None,
    ) -> None:
        data: dict[str, object] = {
            "phase": phase,
            "attempt": attempt,
            "llm": {"provider": llm.provider, "model": llm.model},
            "message_count": len(messages),
            "message_roles": [item.role for item in messages],
            "tool_names": [item.name for item in tools],
            "tool_choice": tool_choice,
        }
        if self._capture_prompts:
            data["request_snapshot"] = provider_request_snapshot(
                messages,
                tools,
                tool_choice=tool_choice,
            )
        await self._record("model.request", data)

    async def model_response(self, phase: str, completion: ChatCompletion) -> None:
        data: dict[str, object] = {
            "phase": phase,
            "finish_reason": completion.finish_reason,
            "content_characters": len(completion.content or ""),
            "tool_call_names": [call.name for call in completion.tool_calls],
        }
        if completion.usage is not None:
            data["usage"] = {
                "prompt_tokens": completion.usage.prompt_tokens,
                "completion_tokens": completion.usage.completion_tokens,
                "total_tokens": completion.usage.total_tokens,
                "cached_tokens": completion.usage.cached_tokens,
            }
        if self._capture_prompts:
            data["response_snapshot"] = {
                "content": completion.content,
                "finish_reason": completion.finish_reason,
                "tool_calls": [
                    {
                        "id": call.id,
                        "name": call.name,
                        "arguments": call.arguments,
                    }
                    for call in completion.tool_calls
                ],
            }
        await self._record("model.response", data)

    async def tool_call(self, call: ToolCall) -> None:
        data: dict[str, object] = {
            "tool_call_id": call.id,
            "name": call.name,
            "argument_count": len(call.arguments),
        }
        if call.name in {"capability_search", "capability_execute"}:
            capability_id = call.arguments.get("capability_id") or call.arguments.get("skill_id")
            role = call.arguments.get("role")
            if isinstance(capability_id, str):
                data["capability_id"] = capability_id
            if role in {"primary", "supporting"}:
                data["skill_role"] = role
        await self._record(
            "tool.call",
            data,
        )

    async def tool_result(
        self,
        call: ToolCall,
        result: dict[str, object],
        *,
        duration_ms: float | None = None,
    ) -> None:
        data: dict[str, object] = {
            "tool_call_id": call.id,
            "name": call.name,
            "status": _string(result.get("status")),
            "code": _string(result.get("code")),
        }
        data.update(_tool_timing_fields(result, duration_ms=duration_ms))
        data.update(_tool_capability_fields(result))
        await self._record("tool.result", data)

    def begin_model_turn(self) -> tuple[int, float]:
        self._model_turn += 1
        return self._model_turn, monotonic()

    async def model_turn_completed(
        self,
        phase: str,
        *,
        turn: int,
        started_at: float,
        tool_call_count: int,
        content_characters: int,
    ) -> None:
        await self.milestone(
            "model_turn_completed",
            phase=phase,
            turn=turn,
            duration_ms=round((monotonic() - started_at) * 1_000, 3),
            tool_call_count=tool_call_count,
            content_characters=content_characters,
        )

    async def queue_wait(self, queue_wait_ms: float) -> None:
        await self.milestone("queue_wait", queue_wait_ms=round(max(0.0, queue_wait_ms), 3))

    async def milestone(self, name: str, **data: object) -> None:
        await self._record(
            "runtime.milestone",
            {
                "name": name,
                "elapsed_ms": self.elapsed_ms(),
                **data,
            },
        )

    async def completion_decision(
        self,
        decision: str,
        reason: str | None,
        observations: tuple[ToolObservation, ...],
    ) -> None:
        counts = {
            kind: sum(item.kind == kind for item in observations)
            for kind in ("control", "instruction", "read", "action", "subagent", "failure")
        }
        await self._record(
            "completion.decision",
            {
                "decision": decision,
                "reason": reason,
                "observation_count": len(observations),
                "observation_kinds": counts,
            },
        )

    def elapsed_ms(self) -> float:
        return round((monotonic() - self._started_at) * 1_000, 3)

    async def _record(self, trace_type: str, data: dict[str, object]) -> None:
        try:
            await self._events.record_trace(
                tenant_id=self._request.tenant_id,
                interaction_id=self._request.interaction_id,
                trace_type=trace_type,
                data=data,
            )
        except Exception:
            logger.exception(
                "Runtime diagnostic trace persistence failed",
                extra={
                    "request_id": self._request.request_id,
                    "tenant_id": self._request.tenant_id,
                    "interaction_id": self._request.interaction_id,
                    "trace_type": trace_type,
                },
            )


def _string(value: object) -> str:
    return value if isinstance(value, str) else ""


def _tool_timing_fields(
    result: dict[str, object], *, duration_ms: float | None
) -> dict[str, object]:
    data: dict[str, object] = {}
    resolved = duration_ms
    if resolved is None:
        raw = result.get("duration_ms")
        if isinstance(raw, (int, float)) and not isinstance(raw, bool):
            resolved = float(raw)
    if resolved is not None:
        data["duration_ms"] = round(resolved, 3)
    embed = result.get("embed_duration_ms")
    if isinstance(embed, (int, float)) and not isinstance(embed, bool):
        data["embed_duration_ms"] = float(embed)
    space_count = result.get("space_count")
    if isinstance(space_count, int) and not isinstance(space_count, bool):
        data["space_count"] = space_count
    retrieval_method = result.get("retrieval_method")
    if isinstance(retrieval_method, str):
        data["retrieval_method"] = retrieval_method
    return data


def _tool_capability_fields(result: dict[str, object]) -> dict[str, object]:
    data: dict[str, object] = {}
    capability = result.get("capability") or result.get("skill")
    if isinstance(capability, dict):
        capability_data = cast(dict[str, object], capability)
        capability_id = capability_data.get("id")
        version = capability_data.get("version")
        if isinstance(capability_id, str):
            data["capability_id"] = capability_id
        if isinstance(version, int) and not isinstance(version, bool):
            data["skill_version"] = version
    if result.get("role") in {"primary", "supporting"}:
        data["skill_role"] = result["role"]
    return data
