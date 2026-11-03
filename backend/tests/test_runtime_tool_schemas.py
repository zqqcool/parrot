from __future__ import annotations

from typing import cast

import pytest
from jsonschema import Draft202012Validator

from app.modules.agent_runtime.builtin_tools import (
    knowledge_search_tool,
    runtime_builtin_tools,
    schedule_tool,
    script_tool,
)
from app.modules.agent_runtime.capability_tools import capability_tools
from app.modules.agent_runtime.contracts import ToolDefinition
from app.modules.agent_runtime.final_response import ask_user_tool, final_response_tool
from app.modules.agent_runtime.subagent_tools import subagent_dispatch_tool
from app.modules.agent_runtime.tool_schema import JsonSchema

_UNSUPPORTED_PROVIDER_KEYWORDS = frozenset(
    {"$defs", "$ref", "allOf", "anyOf", "not", "oneOf", "patternProperties"}
)


def _all_runtime_tools() -> tuple[ToolDefinition, ...]:
    return (
        *runtime_builtin_tools(),
        knowledge_search_tool(),
        *capability_tools(),
        subagent_dispatch_tool(),
        schedule_tool(),
        script_tool(),
        ask_user_tool(),
        final_response_tool(),
    )


@pytest.mark.parametrize("tool", _all_runtime_tools(), ids=lambda tool: tool.name)
def test_runtime_tools_use_the_canonical_schema_authoring_model(tool: ToolDefinition) -> None:
    assert tool.description.strip()
    assert any("\u4e00" <= char <= "\u9fff" for char in tool.description)
    assert isinstance(tool.parameters, JsonSchema)

    schema = tool.argument_schema()
    Draft202012Validator.check_schema(schema)
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    _assert_provider_subset(schema)
    _assert_field_descriptions(schema)


@pytest.mark.parametrize("tool", _all_runtime_tools(), ids=lambda tool: tool.name)
def test_runtime_tool_validation_rejects_unknown_and_null_arguments(
    tool: ToolDefinition,
) -> None:
    valid = _minimum_arguments(tool.name)
    assert tool.accepts_arguments(valid)
    assert not tool.accepts_arguments({**valid, "unexpected": True})

    optional_name = next(
        (name for name in _properties(tool.argument_schema()) if name not in valid),
        None,
    )
    if optional_name is not None:
        assert not tool.accepts_arguments({**valid, optional_name: None})


def test_tool_definition_does_not_expose_its_canonical_schema_for_mutation() -> None:
    tool = ask_user_tool()
    first = tool.argument_schema()
    first["additionalProperties"] = True

    assert tool.argument_schema()["additionalProperties"] is False


def test_schema_authoring_model_copies_properties_and_checks_required_names() -> None:
    properties = {"query": JsonSchema.string("查询。")}
    schema = JsonSchema.object(properties, required=("query",))
    properties["unexpected"] = JsonSchema.boolean()

    assert set(schema.properties) == {"query"}
    with pytest.raises(ValueError, match="not declared"):
        JsonSchema.object({}, required=("missing",))


def test_tool_definition_requires_a_closed_root_object() -> None:
    with pytest.raises(TypeError, match="closed root object"):
        ToolDefinition(
            name="unsafe",
            description="测试开放根对象。",
            parameters=JsonSchema.open_object(),
        )


def _minimum_arguments(tool_name: str) -> dict[str, object]:
    task: dict[str, object] = {
        "objective": "检查实现",
        "source_role": "latest_user_request",
        "source_quote": "检查实现",
        "source_span": {"start": 0, "end": 4},
    }
    minimum_by_tool: dict[str, dict[str, object]] = {
        "memory": {"action": "search"},
        "todo": {},
        "time": {"action": "now"},
        "math": {"action": "evaluate"},
        "knowledge_search": {"query": "发布审批"},
        "capability_search": {"action": "find"},
        "capability_execute": {"capability_id": "capability_test"},
        "subagent_dispatch": {"tasks": [task]},
        "schedule": {"action": "list"},
        "script": {"language": "python", "code": "print(1)"},
        "ask_user": {"question": "请选择环境。"},
        "final_response": {},
    }
    return minimum_by_tool[tool_name]


def _assert_provider_subset(node: object) -> None:
    if isinstance(node, list):
        for item in cast(list[object], node):
            _assert_provider_subset(item)
        return
    if not isinstance(node, dict):
        return
    typed_node = cast(dict[str, object], node)
    assert not (_UNSUPPORTED_PROVIDER_KEYWORDS & set(typed_node))
    assert "title" not in typed_node
    assert "default" not in typed_node
    properties = typed_node.get("properties")
    if isinstance(properties, dict):
        if properties:
            assert typed_node.get("additionalProperties") is False
        for property_schema in cast(dict[str, object], properties).values():
            _assert_provider_subset(property_schema)
    for key, value in typed_node.items():
        if key == "properties":
            continue
        _assert_provider_subset(value)


def _assert_field_descriptions(schema: dict[str, object]) -> None:
    for name, field_schema in _properties(schema).items():
        description = field_schema.get("description")
        assert isinstance(description, str) and description.strip(), name
        assert any("\u4e00" <= char <= "\u9fff" for char in description), name
        _assert_nested_field_descriptions(field_schema)


def _assert_nested_field_descriptions(schema: dict[str, object]) -> None:
    nested_properties = schema.get("properties")
    if isinstance(nested_properties, dict):
        _assert_field_descriptions(schema)
    items = schema.get("items")
    if isinstance(items, dict):
        _assert_nested_field_descriptions(cast(dict[str, object], items))


def _properties(schema: dict[str, object]) -> dict[str, dict[str, object]]:
    properties = schema.get("properties")
    assert isinstance(properties, dict)
    return cast(dict[str, dict[str, object]], properties)
