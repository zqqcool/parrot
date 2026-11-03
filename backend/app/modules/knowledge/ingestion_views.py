from __future__ import annotations

from app.modules.knowledge.models import KnowledgeDocument, KnowledgeIngestionJob
from app.modules.knowledge.schemas import KnowledgeIngestionView


def ingestion_view(
    job: KnowledgeIngestionJob, document: KnowledgeDocument
) -> KnowledgeIngestionView:
    return KnowledgeIngestionView(
        id=job.id,
        title=document.title,
        source_id=job.source_id,
        document_id=document.id,
        document_version_id=job.document_version_id,
        status=job.status,
        attempts=job.attempts,
        error_code=job.error_code,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )
