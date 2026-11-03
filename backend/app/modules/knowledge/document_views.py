from __future__ import annotations

from app.modules.iam.schemas import UserReference
from app.modules.knowledge.models import KnowledgeDocument
from app.modules.knowledge.schemas import KnowledgeDocumentView


def document_view(
    item: KnowledgeDocument,
    version: int,
    chunks: int,
    changed_by_display_name: str,
    changed_by_user: UserReference | None = None,
) -> KnowledgeDocumentView:
    return KnowledgeDocumentView(
        id=item.id,
        tenant_id=item.tenant_id,
        space_id=item.space_id,
        title=item.title,
        source_uri=item.source_uri,
        status=item.status,
        current_version=version,
        chunk_count=chunks,
        changed_by_display_name=changed_by_display_name,
        changed_by_user=changed_by_user,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )
