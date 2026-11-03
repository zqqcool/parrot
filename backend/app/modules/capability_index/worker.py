from __future__ import annotations

from sqlalchemy import select

from app.core.config import AppConfig
from app.infrastructure.credential_cipher import CredentialCipher
from app.infrastructure.db.session import DatabaseManager
from app.modules.agent_runtime.mcp_executor import McpClientExecutor, RuntimeMcpTool
from app.modules.capability_index.documents import mcp_tool_index_text, skill_index_text
from app.modules.capability_index.vector_store import (
    CapabilityVector,
    CapabilityVectorStore,
    MilvusCapabilityVectorStore,
)
from app.modules.knowledge.embedding import (
    KnowledgeEmbeddingPort,
    OpenAiCompatibleKnowledgeEmbedding,
)
from app.modules.mcp_servers.models import McpServer
from app.modules.mcp_servers.runtime_catalog import McpRuntimeCatalog
from app.modules.skills.models import Skill


class CapabilityIndexWorker:
    """TaskIQ handler that replaces live system vectors without database job state."""

    def __init__(
        self,
        settings: AppConfig,
        *,
        cipher: CredentialCipher,
        embeddings: KnowledgeEmbeddingPort | None = None,
        vectors: CapabilityVectorStore | None = None,
    ) -> None:
        self._settings = settings
        self._database = DatabaseManager(settings.database)
        self._embeddings = embeddings or OpenAiCompatibleKnowledgeEmbedding(
            settings, section=settings.capability_index.embedding
        )
        self._vectors = vectors or MilvusCapabilityVectorStore(settings)
        self._mcp = McpClientExecutor(settings, cipher)

    async def close(self) -> None:
        await self._database.dispose()

    async def process(
        self,
        tenant_id: str,
        source_kind: str,
        source_id: str,
        source_revision: str,
    ) -> bool:
        if not self._settings.capability_index.enabled:
            return False
        if source_kind == "skill":
            await self._index_skill(tenant_id, source_id, source_revision)
        elif source_kind == "mcp_server":
            await self._index_mcp_server(tenant_id, source_id, source_revision)
        else:
            raise ValueError("Unsupported capability index source")
        return True

    async def _index_skill(self, tenant_id: str, skill_id: str, revision: str) -> None:
        async with self._database.session() as session:
            await self._database.set_tenant(session, tenant_id)
            skill = await session.scalar(
                select(Skill).where(Skill.tenant_id == tenant_id, Skill.id == skill_id)
            )
        vector_id = f"skill:{skill_id}"
        if skill is None or skill.status != "published":
            await self._vectors.delete((vector_id,))
            return
        if str(skill.version) != revision:
            return
        embedding = await self._embeddings.embed((_skill_text(skill),))
        await self._vectors.upsert(
            (
                CapabilityVector(
                    id=vector_id,
                    tenant_id=tenant_id,
                    source_kind="skill",
                    source_id=skill.id,
                    owner_id=skill.id,
                    vector=embedding[0],
                ),
            )
        )

    async def _index_mcp_server(self, tenant_id: str, server_id: str, revision: str) -> None:
        async with self._database.session() as session:
            await self._database.set_tenant(session, tenant_id)
            server = await session.scalar(
                select(McpServer).where(McpServer.tenant_id == tenant_id, McpServer.id == server_id)
            )
            profiles = await McpRuntimeCatalog(session).get_active(tenant_id, (server_id,))
        if server is None or server.status != "active":
            await self._vectors.delete_owner(tenant_id, server_id)
            return
        if server.updated_at.isoformat() != revision:
            return
        tools = await self._mcp.discover(profiles)
        embeddings = await self._embeddings.embed(tuple(_mcp_text(item) for item in tools))
        await self._vectors.delete_owner(tenant_id, server_id)
        await self._vectors.upsert(
            tuple(
                CapabilityVector(
                    id=item.capability_id,
                    tenant_id=tenant_id,
                    source_kind="mcp",
                    source_id=item.capability_id,
                    owner_id=server_id,
                    vector=embedding,
                )
                for item, embedding in zip(tools, embeddings, strict=True)
            )
        )


def _skill_text(skill: Skill) -> str:
    return skill_index_text(skill.name, skill.description, skill.instructions)


def _mcp_text(tool: RuntimeMcpTool) -> str:
    return mcp_tool_index_text(tool.server_name, tool.tool_name, tool.description)
