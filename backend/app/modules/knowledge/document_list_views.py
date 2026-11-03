from __future__ import annotations

from app.modules.iam.user_references import UserReferenceResolver
from app.modules.knowledge.document_views import document_view
from app.modules.knowledge.models import KnowledgeDocument
from app.modules.knowledge.schemas import KnowledgeDocumentView

DocumentListRow = tuple[KnowledgeDocument, int, int, str, str]


async def document_list_views(
    tenant_id: str,
    rows: list[DocumentListRow],
    user_references: UserReferenceResolver,
) -> list[KnowledgeDocumentView]:
    users = await user_references.resolve(
        tenant_id, (changed_by_user_id for _, _, _, changed_by_user_id, _ in rows)
    )
    return [
        document_view(
            document,
            version,
            chunks,
            changed_by_display_name,
            users.get(changed_by_user_id),
        )
        for document, version, chunks, changed_by_user_id, changed_by_display_name in rows
    ]
