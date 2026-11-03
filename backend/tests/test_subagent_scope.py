from __future__ import annotations

from dataclasses import replace

import pytest
from _agent_runtime_support import profile, request

from app.core.agent_runtime import (
    RuntimeMcpServerProfile,
    RuntimeMcpToolPolicy,
    RuntimeSkillProfile,
)
from app.modules.agent_runtime.subagent_scope import (
    derive_child_profile,
    derive_child_skill_context,
)
from app.modules.agent_runtime.plan_tools import tools_for_plan
from app.modules.agent_runtime.planner import AgentPlan
from app.modules.agent_runtime.taskboard import create_task_board


def test_loop_child_profile_is_a_read_only_subset_of_the_parent() -> None:
    read_policy = _policy("lookup", effect="read", approval="automatic")
    write_policy = _policy("create", effect="side_effect", approval="required")
    parent = replace(
        profile(),
        agent_type_key="knowledge",
        skills=(*profile().skills, _executable_skill()),
        mcp_servers=(_server(read_policy, write_policy),),
    )
    task = _scoped_task(
        {
            "primary_skill": {"skill_id": "skill_test", "skill_version": 1},
            "mcp_capability_ids": ["mcp:server_test:lookup"],
            "knowledge_enabled": True,
        }
    )

    child = derive_child_profile(parent, task, source="agent_loop")

    assert [skill.id for skill in child.skills] == ["skill_test"]
    assert [policy.name for policy in child.mcp_servers[0].tool_policies] == ["lookup"]
    assert child.agent_type_key == "knowledge"
    context = derive_child_skill_context(child, task, source="agent_loop")
    assert context.primary is not None and context.primary.skill_id == "skill_test"
    assert context.supporting == ()


def test_loop_child_scope_rejects_unbound_or_side_effect_capabilities() -> None:
    parent = replace(
        profile(),
        skills=(*profile().skills, _executable_skill()),
        mcp_servers=(_server(_policy("create", "side_effect", "required")),),
    )

    with pytest.raises(ValueError, match="read-only subset"):
        derive_child_profile(
            parent,
            _scoped_task(
                {
                    "supporting_skills": [{"skill_id": "skill_executable", "skill_version": 1}],
                    "mcp_capability_ids": ["mcp:server_test:create"],
                }
            ),
            source="agent_loop",
        )


def test_planner_child_legacy_scope_keeps_only_parent_read_capabilities() -> None:
    read_policy = _policy("lookup", effect="read", approval="automatic")
    write_policy = _policy("create", effect="side_effect", approval="required")
    parent = replace(
        profile(),
        skills=(*profile().skills, _executable_skill()),
        mcp_servers=(_server(read_policy, write_policy),),
    )

    child = derive_child_profile(parent, _scoped_task({}), source="functional_planner")

    assert [skill.id for skill in child.skills] == ["skill_test"]
    assert [policy.name for policy in child.mcp_servers[0].tool_policies] == ["lookup"]


def test_child_loop_does_not_expose_orchestration_or_script_tools() -> None:
    child_request = replace(request(), entry_type="subagent", runtime_depth=1)

    tools = tools_for_plan(
        child_request,
        AgentPlan(action="capability_lookup", synthetic=True),
        script_enabled=True,
        subagent_enabled=True,
    )

    visible = {tool.name for tool in tools}
    assert "capability_search" in visible
    assert visible.isdisjoint({"subagent_dispatch", "schedule", "script", "ask_user"})


def _scoped_task(scope: dict[str, object]):
    board = create_task_board(
        {
            "tasks": [
                {
                    "objective": "Research release notes",
                    "capability_scope": scope,
                    "source_role": "latest_user_request",
                    "source_quote": "Prepare release notes",
                    "source_span": {"start": 0, "end": 21},
                }
            ]
        },
        "Prepare release notes",
        0,
    )
    return board.tasks[0]


def _executable_skill() -> RuntimeSkillProfile:
    return RuntimeSkillProfile(
        id="skill_executable",
        name="writer",
        description="Writes external state",
        instructions="Write",
        manifest={"execute": True, "entrypoint": "main.py"},
        version=1,
    )


def _server(*policies: RuntimeMcpToolPolicy) -> RuntimeMcpServerProfile:
    return RuntimeMcpServerProfile(
        id="server_test",
        name="test",
        transport="streamable_http",
        endpoint="https://example.test/mcp",
        arguments=(),
        encrypted_credentials=(),
        tool_policies=policies,
    )


def _policy(name: str, effect: str, approval: str) -> RuntimeMcpToolPolicy:
    return RuntimeMcpToolPolicy(
        name=name,
        description=name,
        input_schema={"type": "object"},
        schema_hash="sha256:test",
        effect=effect,
        approval=approval,
    )
