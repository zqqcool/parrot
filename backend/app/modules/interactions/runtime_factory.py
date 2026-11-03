from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent_runtime import AgentRuntimeProfileResolver
from app.core.config import AppConfig
from app.core.task_dispatch import TaskDispatcher
from app.infrastructure.credential_cipher import CredentialCipher
from app.infrastructure.db.session import DatabaseManager
from app.infrastructure.skill_package_storage import LocalSkillPackageStorage
from app.modules.agent_runtime.active_skill import SqlSkillContextCheckpointStore
from app.modules.agent_runtime.durable import DurableInProcessRuntime, RuntimeWorker
from app.modules.agent_runtime.in_process import InProcessAgentRuntime
from app.modules.agent_runtime.math_runtime import BuiltinMathRuntime
from app.modules.agent_runtime.mcp_executor import McpClientExecutor
from app.modules.agent_runtime.pending_action import SqlPendingToolActionStore
from app.modules.agent_runtime.script_runtime import SandboxedScriptRuntime
from app.modules.agent_runtime.skill_executor import SandboxedSkillExecutor
from app.modules.agent_runtime.sql_finalization_checkpoint import SqlFinalizationCheckpointStore
from app.modules.agent_runtime.subagent_dispatcher import SqlSubagentDispatcher
from app.modules.agent_runtime.time_runtime import BuiltinTimeRuntime
from app.modules.agents.repository import AgentBindingRepository
from app.modules.agents.runtime_profile import BoundAgentRuntimeProfileResolver
from app.modules.capability_index.hybrid_search import SystemCapabilityHybridSearch
from app.modules.interactions.history import SqlConversationHistory
from app.modules.interactions.runtime import RuntimePort
from app.modules.knowledge.runtime import SqlKnowledgeRuntime
from app.modules.llm_configs.runtime_catalog import LlmRuntimeCatalog
from app.modules.mcp_servers.runtime_catalog import McpRuntimeCatalog
from app.modules.memory.runtime import SqlMemoryRuntime
from app.modules.memory.semantic_search import build_memory_semantic_search
from app.modules.model_providers.llm import ProviderLlmClient
from app.modules.schedules.runtime import SqlScheduleRuntime
from app.modules.skills.runtime_catalog import SkillRuntimeCatalog


def build_runtime(settings: AppConfig, dispatcher: TaskDispatcher) -> RuntimePort:
    return DurableInProcessRuntime(dispatcher, DatabaseManager(settings.database))


def build_runtime_worker(settings: AppConfig, dispatcher: TaskDispatcher) -> RuntimeWorker:
    cipher = CredentialCipher(settings.security.credential_encryption_key.get_secret_value())
    model = ProviderLlmClient(settings, cipher)
    skill_executor = SandboxedSkillExecutor(
        LocalSkillPackageStorage(settings.skills.artifact_directory),
        settings.skills.sandbox,
        settings.skills.max_artifact_bytes,
    )
    database = DatabaseManager(settings.database)
    subagents = SqlSubagentDispatcher(settings, database, dispatcher)
    return RuntimeWorker(
        settings,
        InProcessAgentRuntime(
            model,
            max_tool_rounds=settings.ai.agent_max_tool_rounds,
            max_tool_calls=settings.ai.agent_max_tool_calls,
            max_consecutive_tool_errors=settings.ai.agent_max_consecutive_tool_errors,
            max_model_retries=settings.ai.agent_model_retry_attempts,
            max_control_plane_replans=settings.ai.agent_max_control_plane_replans,
            max_finalization_replans=settings.ai.agent_max_finalization_replans,
            timeout_seconds=settings.runtime.request_timeout_seconds,
            max_parallel_tool_calls=settings.ai.max_parallel_tool_calls,
            capability_exact_repeat_limit=settings.ai.capability_exact_repeat_limit,
            capability_similar_repeat_limit=settings.ai.capability_similar_repeat_limit,
            capability_similarity_threshold=settings.ai.capability_similarity_threshold,
            capture_prompts=settings.ai.debug_capture_prompts,
            direct_rendering_enabled=settings.ai.agent_direct_rendering_enabled,
            loop_subagents_enabled=settings.ai.agent_loop_subagents_enabled,
            max_subagent_tasks=settings.ai.agent_max_subagent_tasks,
            max_supporting_skills=settings.ai.agent_max_supporting_skills,
            history_turns=settings.runtime.history_turns,
            history_max_tokens=settings.runtime.history_max_tokens,
            skill_executor=skill_executor,
            mcp_executor=McpClientExecutor(settings, cipher),
            capability_search=SystemCapabilityHybridSearch(settings),
            memory_runtime=_memory_runtime(settings, database, dispatcher),
            knowledge_runtime=build_knowledge_runtime(settings, database, cipher),
            conversation_history=SqlConversationHistory(database),
            schedule_runtime=SqlScheduleRuntime(
                database, settings.schedules.default_timezone, dispatcher
            ),
            time_runtime=BuiltinTimeRuntime(settings.runtime.default_timezone),
            math_runtime=BuiltinMathRuntime(),
            script_runtime=(
                SandboxedScriptRuntime(
                    settings.skills.sandbox,
                    enabled=True,
                    default_timeout_seconds=settings.runtime.script.default_timeout_seconds,
                    max_timeout_seconds=settings.runtime.script.max_timeout_seconds,
                )
                if settings.runtime.script.enabled
                else None
            ),
            subagent_dispatcher=subagents,
            pending_actions=SqlPendingToolActionStore(database),
            finalization_checkpoints=SqlFinalizationCheckpointStore(database),
            skill_context_checkpoints=SqlSkillContextCheckpointStore(database),
            database=database,
        ),
        database=database,
        subagent_dispatcher=subagents,
    )


def build_profile_resolver(
    settings: AppConfig, session: AsyncSession
) -> AgentRuntimeProfileResolver | None:
    del settings
    return BoundAgentRuntimeProfileResolver(
        AgentBindingRepository(session),
        LlmRuntimeCatalog(session),
        SkillRuntimeCatalog(session),
        McpRuntimeCatalog(session),
    )


def _memory_runtime(
    settings: AppConfig, database: DatabaseManager, dispatcher: TaskDispatcher
) -> SqlMemoryRuntime:
    return SqlMemoryRuntime(
        database,
        settings.memory,
        build_memory_semantic_search(settings),
        dispatcher,
    )


def build_knowledge_runtime(
    settings: AppConfig,
    database: DatabaseManager,
    cipher: CredentialCipher | None = None,
) -> SqlKnowledgeRuntime:
    return SqlKnowledgeRuntime(
        database,
        candidate_multiplier=settings.knowledge.vector.candidate_multiplier,
        reciprocal_rank_constant=settings.knowledge.vector.reciprocal_rank_constant,
        settings=settings,
        cipher=cipher
        or CredentialCipher(settings.security.credential_encryption_key.get_secret_value()),
    )
