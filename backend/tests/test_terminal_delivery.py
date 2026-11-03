from __future__ import annotations

from app.modules.agent_runtime.observations import ToolObservation
from app.modules.agent_runtime.terminal_delivery import terminal_delivery_mode


def test_live_streamed_content_uses_live_delivery() -> None:
    assert terminal_delivery_mode("Short answer.", (), live_streamed=True) == "live"


def test_tool_arg_content_without_live_stream_stays_candidate() -> None:
    observation = ToolObservation(
        tool_name="knowledge_search",
        call_id="call_1",
        kind="read",
        succeeded=True,
        result_status="ok",
    )
    assert terminal_delivery_mode("Any length.", (observation,)) == "candidate"


def test_long_content_without_live_stream_stays_candidate() -> None:
    assert terminal_delivery_mode("x" * 1_000, ()) == "candidate"


def test_signal_only_final_response_uses_final_renderer() -> None:
    assert terminal_delivery_mode("", (), signal_only=True) == "render"
