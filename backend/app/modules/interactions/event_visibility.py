from __future__ import annotations

_PUBLIC_EVENT_TYPES = frozenset(
    {
        "ai.output.delta",
        "ai.output.reset",
        "ai.output.completed",
        "ai.output.cancelled",
        "ai.output.failed",
        "ai.thinking.delta",
        "ai.thinking.completed",
    }
)


def is_public_interaction_event(event_type: str) -> bool:
    """Fail closed for runtime events not explicitly safe for anonymous clients."""

    return event_type in _PUBLIC_EVENT_TYPES
