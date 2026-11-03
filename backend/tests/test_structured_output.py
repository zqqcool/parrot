from __future__ import annotations

import pytest

from app.modules.agent_runtime.structured_output import (
    StructuredOutputError,
    decode_json_object,
)


def test_decodes_plain_json_object() -> None:
    assert decode_json_object('{"action":"direct_answer"}') == {"action": "direct_answer"}


def test_decodes_one_json_markdown_fence() -> None:
    assert decode_json_object('```json\n{"knowledge_queries":["policy"]}\n```') == {
        "knowledge_queries": ["policy"]
    }


@pytest.mark.parametrize(
    "value",
    (
        'prefix {"action":"direct_answer"}',
        '```python\n{"action":"direct_answer"}\n```',
        '```json\n{"action":"direct_answer"}\n``` trailing',
        '[{"action":"direct_answer"}]',
    ),
)
def test_rejects_ambiguous_or_non_object_output(value: str) -> None:
    with pytest.raises(StructuredOutputError):
        decode_json_object(value)
