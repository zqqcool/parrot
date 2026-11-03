from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from app.core.clock import utc_now
from app.core.ids import new_id
from app.core.task_dispatch import TaskDispatcher
from app.modules.embedding_configs.models import EmbeddingConfig
from app.modules.knowledge.embedding_profile import embedding_snapshot_matches
from app.modules.knowledge.models import (
    KnowledgeDocument,
    KnowledgeDocumentVersion,
    KnowledgeSpace,
    KnowledgeVectorIndexJob,
)


def knowledge_space_index_status(statuses: Iterable[str]) -> str:
    values = set(statuses)
    if "failed" in values:
        return "failed"
    if values.intersection(("queued", "running")):
        return "pending"
    return "ready"


def knowledge_space_index_target_statement(
    *,
    tenant_id: str,
    document_version_id: str,
    embedding_config_id: str,
    index_revision: int,
) -> Select[tuple[KnowledgeSpace]]:
    return (
        select(KnowledgeSpace)
        .join(
            KnowledgeDocument,
            (KnowledgeDocument.tenant_id == KnowledgeSpace.tenant_id)
            & (KnowledgeDocument.space_id == KnowledgeSpace.id),
        )
        .join(
            KnowledgeDocumentVersion,
            (KnowledgeDocumentVersion.tenant_id == KnowledgeDocument.tenant_id)
            & (KnowledgeDocumentVersion.document_id == KnowledgeDocument.id),
        )
        .where(
            KnowledgeSpace.tenant_id == tenant_id,
            KnowledgeDocumentVersion.id == document_version_id,
            KnowledgeSpace.embedding_config_id == embedding_config_id,
            KnowledgeSpace.retrieval_index_revision == index_revision,
        )
        .with_for_update(of=KnowledgeSpace)
    )


def knowledge_space_index_statuses_statement(
    *,
    tenant_id: str,
    space_id: str,
    embedding_config_id: str,
    index_revision: int,
) -> Select[tuple[str]]:
    return (
        select(KnowledgeVectorIndexJob.status)
        .join(
            KnowledgeDocumentVersion,
            (KnowledgeDocumentVersion.tenant_id == KnowledgeVectorIndexJob.tenant_id)
            & (KnowledgeDocumentVersion.id == KnowledgeVectorIndexJob.document_version_id),
        )
        .join(
            KnowledgeDocument,
            (KnowledgeDocument.tenant_id == KnowledgeDocumentVersion.tenant_id)
            & (KnowledgeDocument.id == KnowledgeDocumentVersion.document_id),
        )
        .where(
            KnowledgeVectorIndexJob.tenant_id == tenant_id,
            KnowledgeDocument.tenant_id == tenant_id,
            KnowledgeDocument.space_id == space_id,
            KnowledgeVectorIndexJob.embedding_config_id == embedding_config_id,
            KnowledgeVectorIndexJob.index_revision == index_revision,
        )
    )


async def enqueue_vector_job(
    session: AsyncSession,
    tenant_id: str,
    document_version_id: str,
    action: str,
    *,
    embedding_config_id: str | None = None,
    index_revision: int | None = None,
    dispatcher: TaskDispatcher | None = None,
) -> bool:
    if embedding_config_id is None or index_revision is None:
        result = await session.execute(
            select(KnowledgeSpace)
            .join(
                KnowledgeDocument,
                (KnowledgeDocument.tenant_id == KnowledgeSpace.tenant_id)
                & (KnowledgeDocument.space_id == KnowledgeSpace.id),
            )
            .join(
                KnowledgeDocumentVersion,
                (KnowledgeDocumentVersion.tenant_id == KnowledgeDocument.tenant_id)
                & (KnowledgeDocumentVersion.document_id == KnowledgeDocument.id),
            )
            .where(
                KnowledgeSpace.tenant_id == tenant_id,
                KnowledgeDocumentVersion.id == document_version_id,
            )
        )
        space = result.scalar_one_or_none()
        if space is None or space.embedding_config_id is None:
            return False
        embedding_config_id = space.embedding_config_id
        index_revision = space.retrieval_index_revision
    else:
        space = None
    if action == "upsert":
        if space is None:
            space = await session.scalar(
                select(KnowledgeSpace)
                .join(
                    KnowledgeDocument,
                    (KnowledgeDocument.tenant_id == KnowledgeSpace.tenant_id)
                    & (KnowledgeDocument.space_id == KnowledgeSpace.id),
                )
                .join(
                    KnowledgeDocumentVersion,
                    (KnowledgeDocumentVersion.tenant_id == KnowledgeDocument.tenant_id)
                    & (KnowledgeDocumentVersion.document_id == KnowledgeDocument.id),
                )
                .where(
                    KnowledgeSpace.tenant_id == tenant_id,
                    KnowledgeDocumentVersion.id == document_version_id,
                    KnowledgeSpace.embedding_config_id == embedding_config_id,
                    KnowledgeSpace.retrieval_index_revision == index_revision,
                )
            )
        profile = await session.scalar(
            select(EmbeddingConfig).where(
                EmbeddingConfig.tenant_id == tenant_id,
                EmbeddingConfig.id == embedding_config_id,
            )
        )
        if space is None or profile is None or not embedding_snapshot_matches(space, profile):
            raise ValueError("Knowledge space Embedding snapshot is unavailable or incompatible")
        space.retrieval_index_status = "pending"
    statement = insert(KnowledgeVectorIndexJob).values(
        id=new_id("knowledge_vector_job"),
        tenant_id=tenant_id,
        document_version_id=document_version_id,
        embedding_config_id=embedding_config_id,
        index_revision=index_revision,
        action=action,
    )
    result = await session.execute(
        statement.on_conflict_do_update(
            constraint="uq_knowledge_vector_job_profile_version",
            set_={
                "status": "queued",
                "attempts": 0,
                "lease_owner": None,
                "lease_until": None,
                "error_code": None,
                "updated_at": utc_now(),
            },
            where=KnowledgeVectorIndexJob.status.in_(("failed", "succeeded")),
        ).returning(KnowledgeVectorIndexJob.id)
    )
    job_id = result.scalar_one_or_none()
    if job_id is not None and dispatcher is not None:
        await dispatcher.dispatch_knowledge_vector(tenant_id, job_id)
    return job_id is not None
