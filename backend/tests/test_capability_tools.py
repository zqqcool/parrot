from __future__ import annotations

from typing import cast

from app.modules.agent_runtime.capability_tools import capability_tools


def test_capability_tools_publish_capability_id_and_skill_role() -> None:
    by_name = {tool.name: tool for tool in capability_tools()}
    search = by_name["capability_search"]
    execute = by_name["capability_execute"]
    search_properties = _properties(search.argument_schema())
    execute_properties = _properties(execute.argument_schema())

    assert "capability_id" in search_properties
    assert "capability_id" in execute_properties
    assert "skill_id" not in search_properties
    assert "skill_id" not in execute_properties
    assert search_properties["action"]["enum"] == ["find", "load", "find_and_load"]
    assert search_properties["role"]["enum"] == ["primary", "supporting"]
    assert execute.argument_schema()["required"] == ["capability_id"]
    assert execute_properties["input"]["additionalProperties"] is True

    assert search.accepts_arguments({"action": "find"})
    assert not search.accepts_arguments({"action": "unknown"})
    assert not execute.accepts_arguments({"capability_id": "cap", "unknown": True})


def _properties(schema: dict[str, object]) -> dict[str, dict[str, object]]:
    properties = schema.get("properties")
    assert isinstance(properties, dict)
    return cast(dict[str, dict[str, object]], properties)
