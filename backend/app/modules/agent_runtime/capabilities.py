from __future__ import annotations

from dataclasses import dataclass, field
from typing import cast

from app.core.agent_runtime import (
    DEFAULT_CAPABILITY_RELEVANCE_THRESHOLD,
    RuntimeMcpServerProfile,
    RuntimeSkillProfile,
)
from app.modules.agent_runtime.active_skill import (
    ActiveSkillCheckpointPort,
    SkillContextCheckpointPort,
    SkillRole,
    active_skill_unavailable,
)
from app.modules.agent_runtime.approved_mcp_execution import execute_approved_mcp
from app.modules.agent_runtime.capability_presentation import (
    bounded_instructions,
    capability_failure,
    lexical_ranking,
    mcp_index_document,
    mcp_tool_view,
    skill_index_document,
    skill_view,
)
from app.modules.agent_runtime.contracts import ToolCall
from app.modules.agent_runtime.mcp_executor import McpExecutor, RuntimeMcpTool
from app.modules.agent_runtime.skill_context_profiles import (
    current_skill_context,
    pinned_skill,
    unavailable_pinned_skill,
)
from app.modules.agent_runtime.skill_executor import SkillExecutionContext, SkillExecutor
from app.modules.capability_index.hybrid_search import CapabilitySearchRanker
from app.modules.capability_index.ranking import CapabilitySearchDocument
from app.modules.interactions.runtime import (
    RuntimeActiveSkill,
    RuntimeSkillContext,
)
from app.modules.mcp_servers.tool_policy import (
    arguments_match_schema,
    automatic_read_policy,
    enabled_tool_policy,
    parallel_safe_policy,
    policy_for_tool,
)


@dataclass
class CapabilitySession:
    skills: tuple[RuntimeSkillProfile, ...]
    mcp_servers: tuple[RuntimeMcpServerProfile, ...] = ()
    minimum_relevance_score: float = DEFAULT_CAPABILITY_RELEVANCE_THRESHOLD
    loaded_skill_ids: set[str] = field(default_factory=set[str])
    active_skill: RuntimeActiveSkill | None = None
    skill_context: RuntimeSkillContext | None = None
    max_supporting_skills: int = 3
    active_skill_checkpoints: ActiveSkillCheckpointPort | None = None
    skill_context_checkpoints: SkillContextCheckpointPort | None = None
    skill_executor: SkillExecutor | None = None
    execution_context: SkillExecutionContext | None = None
    mcp_executor: McpExecutor | None = None
    search_ranker: CapabilitySearchRanker | None = None
    knowledge_only: bool = False
    approval_supported: bool = True
    _mcp_tools: tuple[RuntimeMcpTool, ...] | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        if self.skill_context is None:
            self.skill_context = RuntimeSkillContext(primary=self.active_skill)
        elif self.active_skill is None:
            self.active_skill = self.skill_context.primary

    def is_parallel_safe_call(self, call: ToolCall) -> bool:
        capability_id = call.arguments.get("capability_id")
        if call.name != "capability_execute" or not isinstance(capability_id, str):
            return False
        tool = next(
            (item for item in self._mcp_tools or () if item.capability_id == capability_id), None
        )
        if tool is None:
            return False
        server = next((item for item in self.mcp_servers if item.id == tool.server_id), None)
        return server is not None and parallel_safe_policy(server, tool) is not None

    async def search(
        self,
        action: object,
        query: object,
        skill_id: object,
        role: object = "primary",
    ) -> dict[str, object]:
        context = current_skill_context(self.skill_context, self.active_skill)
        if unavailable := unavailable_pinned_skill(self.skills, context):
            return active_skill_unavailable(unavailable)
        normalized_action = str(action or "").casefold()
        if normalized_action == "find":
            return await self._find(str(query or ""))
        if normalized_action == "load":
            return await self._load(str(skill_id or ""), str(role or "primary").casefold())
        if normalized_action == "find_and_load":
            return await self._find_and_load(
                str(query or ""), str(role or "primary").casefold()
            )
        return capability_failure(
            "CAPABILITY_ACTION_INVALID", "Only find, load, and find_and_load actions are supported"
        )

    async def execute(self, skill_id: object, input_payload: object = None) -> dict[str, object]:
        requested_id = str(skill_id or "")
        selected = self._skill(requested_id)
        if selected is None:
            return await self._execute_mcp(requested_id, input_payload)
        context = current_skill_context(self.skill_context, self.active_skill)
        if pinned := pinned_skill(context, selected.id):
            if selected.version != pinned.skill_version:
                return active_skill_unavailable(pinned)
        if self.knowledge_only and not selected.is_instruction_only:
            return capability_failure(
                "KNOWLEDGE_CAPABILITY_NOT_ALLOWED",
                "Knowledge Agents may use instruction-only Skills but cannot execute packages",
            )
        if selected.id not in self.loaded_skill_ids:
            return capability_failure(
                "SKILL_INSTRUCTIONS_NOT_LOADED",
                "Load the Skill instructions before requesting execution",
            )
        if selected.requires_mcp:
            return capability_failure(
                "MCP_EXECUTION_NOT_ENABLED",
                "MCP execution is not enabled in the Parrot in-process runtime",
            )
        if selected.is_executable:
            if self.skill_executor is None or self.execution_context is None:
                return capability_failure(
                    "SKILL_EXECUTION_NOT_ENABLED",
                    "Executable Skill packages require a configured sandboxed executor",
                )
            if input_payload is not None and not isinstance(input_payload, dict):
                return capability_failure(
                    "SKILL_INPUT_INVALID", "Skill execution input must be a JSON object"
                )
            return await self.skill_executor.execute(
                selected,
                self.execution_context,
                cast(dict[str, object], input_payload) if isinstance(input_payload, dict) else {},
            )
        return {
            "status": "instruction_ready",
            "skill": skill_view(selected),
            "instructions": bounded_instructions(selected.instructions),
            "execution": (
                "Follow the loaded instructions; do not claim external execution occurred."
            ),
        }

    async def _find(self, query: str) -> dict[str, object]:
        skills = self._available_skills()
        mcp_tools = await self._discovered_mcp_tools()
        documents = tuple(
            [CapabilitySearchDocument(item.id, skill_index_document(item)) for item in skills]
            + [
                CapabilitySearchDocument(item.capability_id, mcp_index_document(item))
                for item in mcp_tools
            ]
        )
        views = {
            **{item.id: skill_view(item) for item in skills},
            **{item.capability_id: mcp_tool_view(item) for item in mcp_tools},
        }
        ranking = (
            await self.search_ranker.rank(
                self.execution_context.tenant_id,
                query,
                documents,
                minimum_relevance_score=self.minimum_relevance_score,
            )
            if self.search_ranker is not None and self.execution_context is not None
            else lexical_ranking(query, documents)
        )
        return {
            "status": "ok",
            "capabilities": [views[source_id] for source_id in ranking[:2] if source_id in views],
        }

    async def _find_and_load(self, query: str, role: str) -> dict[str, object]:
        """Rank candidates and load the top Skill when the query is non-empty.

        Empty queries only list candidates (same as find) so cold listing cannot pin a
        Primary by document order. MCP-only rankings are returned without Skill load.
        """
        found = await self._find(query)
        if found.get("status") != "ok":
            return found
        capabilities = found.get("capabilities")
        if not isinstance(capabilities, list):
            return found
        if not query.strip():
            return found
        skill_id = next(
            (
                cast(str, item["id"])
                for item in cast(list[object], capabilities)
                if isinstance(item, dict)
                and item.get("kind") == "skill"
                and isinstance(item.get("id"), str)
            ),
            None,
        )
        if skill_id is None:
            return found
        loaded = await self._load(skill_id, role)
        if loaded.get("status") != "ok":
            return {
                "status": loaded.get("status", "rejected"),
                "code": loaded.get("code"),
                "message": loaded.get("message"),
                "capabilities": capabilities,
            }
        return {
            "status": "ok",
            "capabilities": capabilities,
            "role": loaded.get("role"),
            "capability": loaded.get("capability"),
            "instructions": loaded.get("instructions"),
        }

    async def _load(self, skill_id: str, role: str) -> dict[str, object]:
        selected = self._skill(skill_id)
        if role not in {"primary", "supporting"}:
            return capability_failure(
                "SKILL_ROLE_INVALID", "Skill role must be primary or supporting"
            )
        context = current_skill_context(self.skill_context, self.active_skill)
        if selected is not None and (pinned := pinned_skill(context, selected.id)):
            if selected.version != pinned.skill_version:
                return active_skill_unavailable(pinned)
        if selected is not None and self.knowledge_only and not selected.is_instruction_only:
            return capability_failure(
                "KNOWLEDGE_CAPABILITY_NOT_ALLOWED",
                "Knowledge Agents may load instruction-only Skills only",
            )
        if selected is None:
            tool = next(
                (
                    item
                    for item in await self._discovered_mcp_tools()
                    if item.capability_id == skill_id
                ),
                None,
            )
            if tool is None:
                return capability_failure(
                    "CAPABILITY_NOT_FOUND", "Capability is not available to this agent"
                )
            return {"status": "ok", "capability": mcp_tool_view(tool)}
        activated = (
            await self._activate(selected)
            if role == "primary"
            else await self._activate_supporting(selected)
        )
        if not activated:
            return capability_failure(
                "SKILL_CONTEXT_CONFLICT",
                "The requested Skill cannot be added to this interaction context",
            )
        self.loaded_skill_ids.add(selected.id)
        return {
            "status": "ok",
            "role": role,
            "capability": skill_view(selected),
            "instructions": bounded_instructions(selected.instructions),
        }

    def _skill(self, skill_id: str) -> RuntimeSkillProfile | None:
        return next((item for item in self.skills if item.id == skill_id), None)

    def _available_skills(self) -> tuple[RuntimeSkillProfile, ...]:
        if not self.knowledge_only:
            return self.skills
        return tuple(item for item in self.skills if item.is_instruction_only)

    async def _activate(self, skill: RuntimeSkillProfile) -> bool:
        requested = RuntimeActiveSkill(skill_id=skill.id, skill_version=skill.version)
        if self.active_skill is not None:
            return self.active_skill == requested
        if self.skill_context_checkpoints is not None:
            return await self._pin_context(skill, "primary")
        if self.active_skill_checkpoints is not None:
            if self.execution_context is None:
                return False
            if not await self.active_skill_checkpoints.activate(
                tenant_id=self.execution_context.tenant_id,
                interaction_id=self.execution_context.interaction_id,
                skill_id=skill.id,
                skill_version=skill.version,
            ):
                return False
        self.active_skill = requested
        self.skill_context = RuntimeSkillContext(
            primary=requested,
            supporting=self.skill_context.supporting if self.skill_context is not None else (),
        )
        return True

    async def _activate_supporting(self, skill: RuntimeSkillProfile) -> bool:
        requested = RuntimeActiveSkill(skill_id=skill.id, skill_version=skill.version)
        context = self.skill_context or RuntimeSkillContext(primary=self.active_skill)
        if context.primary is not None and context.primary.skill_id == skill.id:
            return context.primary == requested
        existing = next(
            (item for item in context.supporting if item.skill_id == skill.id),
            None,
        )
        if existing is not None:
            return existing == requested
        if len(context.supporting) >= self.max_supporting_skills:
            return False
        if self.skill_context_checkpoints is not None:
            return await self._pin_context(skill, "supporting")
        self.skill_context = RuntimeSkillContext(
            primary=context.primary,
            supporting=(*context.supporting, requested),
        )
        return True

    async def _pin_context(self, skill: RuntimeSkillProfile, role: str) -> bool:
        if self.skill_context_checkpoints is None or self.execution_context is None:
            return False
        context = await self.skill_context_checkpoints.pin(
            tenant_id=self.execution_context.tenant_id,
            interaction_id=self.execution_context.interaction_id,
            role=cast(SkillRole, role),
            skill_id=skill.id,
            skill_version=skill.version,
        )
        if context is None:
            return False
        self.skill_context = context
        self.active_skill = context.primary
        return True

    async def _discovered_mcp_tools(self) -> tuple[RuntimeMcpTool, ...]:
        if self._mcp_tools is None:
            servers = (
                tuple(server for server in self.mcp_servers if not server.is_local_process)
                if self.knowledge_only or not self.approval_supported
                else self.mcp_servers
            )
            discovered = await self.mcp_executor.discover(servers) if self.mcp_executor else ()
            if self.knowledge_only or not self.approval_supported:
                by_id = {server.id: server for server in servers}
                policy_check = (
                    enabled_tool_policy if self.approval_supported else automatic_read_policy
                )
                self._mcp_tools = tuple(
                    tool
                    for tool in discovered
                    if (server := by_id.get(tool.server_id)) is not None
                    and policy_check(server, tool) is not None
                )
            else:
                self._mcp_tools = discovered
        return self._mcp_tools

    async def _execute_mcp(self, capability_id: str, input_payload: object) -> dict[str, object]:
        if self.mcp_executor is None:
            return capability_failure("MCP_EXECUTION_NOT_ENABLED", "MCP execution is not enabled")
        if not isinstance(input_payload, dict):
            return capability_failure(
                "MCP_INPUT_INVALID", "MCP execution input must be a JSON object"
            )
        tool = next(
            (
                item
                for item in await self._discovered_mcp_tools()
                if item.capability_id == capability_id
            ),
            None,
        )
        if tool is None:
            return capability_failure(
                "MCP_CAPABILITY_NOT_FOUND", "MCP capability must be discovered first"
            )
        server = next((item for item in self.mcp_servers if item.id == tool.server_id), None)
        if server is None:
            return capability_failure(
                "MCP_POLICY_FORBIDDEN", "MCP tool is not approved for execution"
            )
        policy = policy_for_tool(server, tool)
        if policy is None or policy.approval == "forbidden":
            return capability_failure(
                "MCP_POLICY_FORBIDDEN", "MCP tool is not approved for execution"
            )
        arguments = cast(dict[str, object], input_payload)
        if not arguments_match_schema(arguments, policy.input_schema):
            return capability_failure(
                "MCP_INPUT_INVALID", "MCP execution input does not match its Schema"
            )
        if policy.approval == "required":
            if not self.approval_supported:
                return capability_failure(
                    "MCP_APPROVAL_UNSUPPORTED",
                    "This interaction entry cannot resolve an approval.",
                )
            return {
                "status": "approval_required",
                "code": "MCP_APPROVAL_REQUIRED",
                "message": "This action requires explicit approval.",
                "pending_action": {
                    "capability_id": tool.capability_id,
                    "server_id": tool.server_id,
                    "tool_name": tool.tool_name,
                    "arguments": arguments,
                    "schema_hash": policy.schema_hash,
                    "effect": policy.effect,
                    "approval": policy.approval,
                },
            }
        if automatic_read_policy(server, tool) is None:
            return capability_failure(
                "MCP_POLICY_FORBIDDEN", "MCP tool is not approved for execution"
            )
        return await self.mcp_executor.execute(tool, arguments)

    async def execute_approved(
        self,
        capability_id: str,
        input_payload: dict[str, object],
        expected_schema_hash: str,
    ) -> dict[str, object]:
        return await execute_approved_mcp(
            executor=self.mcp_executor,
            tools=await self._discovered_mcp_tools(),
            servers=self.mcp_servers,
            capability_id=capability_id,
            input_payload=input_payload,
            expected_schema_hash=expected_schema_hash,
        )
