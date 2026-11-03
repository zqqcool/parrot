from __future__ import annotations

import hashlib
import logging
from dataclasses import replace

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import Clock
from app.core.ids import new_id
from app.core.object_storage import ObjectStoragePort
from app.core.task_dispatch import TaskDispatcher
from app.modules.knowledge.chunking import split_content
from app.modules.knowledge.extraction.types import ExtractedDocument, ExtractedMedia
from app.modules.knowledge.media_models import KnowledgeEvidenceGroup, KnowledgeMediaAsset
from app.modules.knowledge.media_storage import write_media_object
from app.modules.knowledge.media_types import filter_supported_media, media_file_extension
from app.modules.knowledge.models import (
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeDocumentVersion,
    KnowledgeIngestionJob,
    KnowledgeSource,
)
from app.modules.knowledge.preprocessing import KnowledgeTextProcessingError, process_content
from app.modules.knowledge.rendering import CompositeSlideRenderer
from app.modules.knowledge.vector_jobs import enqueue_vector_job

_STRUCTURED_PROFILES = frozenset({"pptx", "docx", "xlsx"})
logger = logging.getLogger(__name__)


async def publish_extracted_document(
    session: AsyncSession,
    *,
    tenant_id: str,
    source_id: str,
    job: KnowledgeIngestionJob,
    version: KnowledgeDocumentVersion,
    document: KnowledgeDocument,
    extracted: ExtractedDocument,
    clock: Clock,
    dispatcher: TaskDispatcher | None,
    object_storage: ObjectStoragePort | None = None,
) -> None:
    source = await session.scalar(
        select(KnowledgeSource).where(
            KnowledgeSource.tenant_id == tenant_id,
            KnowledgeSource.id == source_id,
        )
    )
    if source is None:
        return
    original_media_count = len(extracted.media)
    extracted = filter_supported_media(extracted)
    unsupported_media_count = original_media_count - len(extracted.media)
    if unsupported_media_count:
        logger.warning(
            "Unsupported knowledge media skipped",
            extra={
                "tenant_id": tenant_id,
                "source_id": source_id,
                "document_version_id": version.id,
                "skipped_media_count": unsupported_media_count,
            },
        )
    await _clear_version_children(session, tenant_id, version.id)
    if extracted.format_profile in _STRUCTURED_PROFILES:
        processed, media_count = await _publish_structured(
            session,
            tenant_id=tenant_id,
            version=version,
            document=document,
            extracted=extracted,
            object_storage=object_storage,
        )
    else:
        processed = await _publish_plain_text(
            session,
            tenant_id=tenant_id,
            version=version,
            document=document,
            extracted=extracted,
        )
        media_count = len(extracted.media)
    now = clock.now()
    if job.action == "replace":
        await _supersede_previous(
            session,
            tenant_id=tenant_id,
            document=document,
            version_id=version.id,
            dispatcher=dispatcher,
        )
    source.status = "completed"
    document.status = "active"
    document.source_id = source.id
    document.title = source.title
    version.content = processed
    version.content_sha256 = hashlib.sha256(processed.encode("utf-8")).hexdigest()
    version.status = "published"
    version.extraction_status = "completed"
    version.format_profile = extracted.format_profile
    version.extractor_name = extracted.extractor_name
    version.extractor_version = extracted.extractor_version
    version.slide_count = extracted.slide_count
    version.sheet_count = extracted.sheet_count
    version.section_count = extracted.section_count
    version.media_count = media_count
    version.skipped_media_count = extracted.skipped_media_count
    version.published_at = now
    await enqueue_vector_job(session, tenant_id, version.id, "upsert", dispatcher=dispatcher)
    job.status = "succeeded"
    job.error_code = None
    job.lease_owner = None
    job.lease_until = None


async def _clear_version_children(session: AsyncSession, tenant_id: str, version_id: str) -> None:
    await session.execute(
        delete(KnowledgeChunk).where(
            KnowledgeChunk.tenant_id == tenant_id,
            KnowledgeChunk.document_version_id == version_id,
        )
    )
    await session.execute(
        delete(KnowledgeMediaAsset).where(
            KnowledgeMediaAsset.tenant_id == tenant_id,
            KnowledgeMediaAsset.document_version_id == version_id,
        )
    )
    await session.execute(
        delete(KnowledgeEvidenceGroup).where(
            KnowledgeEvidenceGroup.tenant_id == tenant_id,
            KnowledgeEvidenceGroup.document_version_id == version_id,
        )
    )


async def _publish_plain_text(
    session: AsyncSession,
    *,
    tenant_id: str,
    version: KnowledgeDocumentVersion,
    document: KnowledgeDocument,
    extracted: ExtractedDocument,
) -> str:
    canonical = extracted.joined_index_text()
    processed = process_content(
        canonical,
        normalize_whitespace=version.normalize_whitespace,
        remove_urls_and_emails=version.remove_urls_and_emails,
    )
    chunks = split_content(
        processed,
        version.chunk_size_chars,
        version.chunk_overlap_chars,
        version.chunk_separator,
    )
    session.add_all(
        KnowledgeChunk(
            id=new_id("knowledge_chunk"),
            tenant_id=tenant_id,
            space_id=document.space_id,
            document_version_id=version.id,
            ordinal=ordinal,
            content=chunk,
            citation_anchor=f"chunk-{ordinal}",
            format_profile=extracted.format_profile,
            block_kind=extracted.blocks[0].block_kind if extracted.blocks else "plain",
            search_vector=func.to_tsvector("simple", chunk),
        )
        for ordinal, chunk in enumerate(chunks, start=1)
    )
    return processed


async def _publish_structured(
    session: AsyncSession,
    *,
    tenant_id: str,
    version: KnowledgeDocumentVersion,
    document: KnowledgeDocument,
    extracted: ExtractedDocument,
    object_storage: ObjectStoragePort | None,
) -> tuple[str, int]:
    group_ids: dict[str, str] = {}
    for group in extracted.groups:
        group_id = new_id("knowledge_evidence_group")
        group_ids[group.key] = group_id
        session.add(
            KnowledgeEvidenceGroup(
                id=group_id,
                tenant_id=tenant_id,
                space_id=document.space_id,
                document_version_id=version.id,
                kind=group.kind,
                title=group.title[:300],
                expand_default=group.expand_default,
                ordinal_start=group.ordinal_start,
                ordinal_end=group.ordinal_end,
            )
        )
    await session.flush()
    if object_storage is not None:
        await _persist_media(
            session,
            tenant_id=tenant_id,
            space_id=document.space_id,
            version_id=version.id,
            group_ids=group_ids,
            media=extracted.media,
            object_storage=object_storage,
        )
    ordinal = 0
    texts: list[str] = []
    for block in extracted.blocks:
        try:
            processed = process_content(
                block.index_text,
                normalize_whitespace=version.normalize_whitespace,
                remove_urls_and_emails=version.remove_urls_and_emails,
            )
        except KnowledgeTextProcessingError:
            processed = block.index_text.strip()
            if not processed:
                continue
        pieces = split_content(
            processed,
            version.chunk_size_chars,
            version.chunk_overlap_chars,
            version.chunk_separator,
        ) or (processed,)
        for piece in pieces:
            ordinal += 1
            texts.append(piece)
            session.add(
                KnowledgeChunk(
                    id=new_id("knowledge_chunk"),
                    tenant_id=tenant_id,
                    space_id=document.space_id,
                    document_version_id=version.id,
                    group_id=group_ids.get(block.group_key or ""),
                    ordinal=ordinal,
                    content=piece,
                    citation_anchor=block.citation_anchor or f"block-{block.slide_no or ordinal}",
                    format_profile=extracted.format_profile,
                    block_kind=block.block_kind,
                    page_kind=block.page_kind,
                    slide_no=block.slide_no,
                    sheet_name=block.sheet_name,
                    section_path=block.section_path,
                    step_label=block.step_label,
                    cell_anchor=block.cell_anchor,
                    search_vector=func.to_tsvector("simple", piece),
                )
            )
    if not texts:
        raise KnowledgeTextProcessingError("KNOWLEDGE_DOCUMENT_EMPTY_AFTER_PROCESSING")
    stored_count = len(extracted.media) if object_storage is not None else 0
    return "\n\n".join(texts), stored_count


def prepare_slide_media(
    extracted: ExtractedDocument, source_bytes: bytes | None
) -> ExtractedDocument:
    if extracted.format_profile != "pptx":
        return extracted
    rendered, fallback_count = _slide_render_media(extracted, source_bytes)
    warnings = extracted.warnings
    if fallback_count:
        warnings = (*warnings, "slide_render_fallback")
    return replace(
        extracted,
        media=(*extracted.media, *rendered),
        skipped_media_count=extracted.skipped_media_count + fallback_count,
        warnings=warnings,
    )


def _slide_render_media(
    extracted: ExtractedDocument, source_bytes: bytes | None
) -> tuple[tuple[ExtractedMedia, ...], int]:
    renderer = CompositeSlideRenderer(enabled=True)
    renderer.prepare_deck(source_bytes)
    embedded_by_slide: dict[int, list[bytes]] = {}
    for item in extracted.media:
        if item.slide_no is None:
            continue
        embedded_by_slide.setdefault(item.slide_no, []).append(item.content)
    renders: list[ExtractedMedia] = []
    fallback_count = 0
    for block in extracted.blocks:
        if block.slide_no is None:
            continue
        title = block.step_label or (block.index_text.split("\n", 1)[0] if block.index_text else "")
        rendered = renderer.render_preview(
            slide_no=block.slide_no,
            title=title,
            body=block.index_text,
            embedded=tuple(embedded_by_slide.get(block.slide_no, ())),
        )
        if not rendered.full_slide:
            fallback_count += 1
        renders.append(
            ExtractedMedia(
                asset_kind="slide_render" if rendered.full_slide else "thumb",
                content=rendered.content,
                content_type=rendered.content_type,
                slide_no=block.slide_no,
                group_key=block.group_key,
                ordinal_in_group=0,
            )
        )
    return tuple(renders), fallback_count


async def _persist_media(
    session: AsyncSession,
    *,
    tenant_id: str,
    space_id: str,
    version_id: str,
    group_ids: dict[str, str],
    media: tuple[ExtractedMedia, ...],
    object_storage: ObjectStoragePort,
) -> None:
    for item in media:
        digest = hashlib.sha256(item.content).hexdigest()
        extension = media_file_extension(item.content_type)
        object_key = (
            f"{tenant_id}/{space_id}/{version_id}/media/"
            f"{item.asset_kind}-{item.slide_no or item.sheet_name or 'doc'}-"
            f"{item.ordinal_in_group}-{digest[:12]}{extension}"
        )
        await write_media_object(object_storage, object_key, item.content, item.content_type)
        session.add(
            KnowledgeMediaAsset(
                id=new_id("knowledge_media_asset"),
                tenant_id=tenant_id,
                space_id=space_id,
                document_version_id=version_id,
                group_id=group_ids.get(item.group_key or "") if item.group_key else None,
                asset_kind=item.asset_kind,
                object_key=object_key,
                content_type=item.content_type,
                content_sha256=digest,
                byte_size=len(item.content),
                width=item.width,
                height=item.height,
                slide_no=item.slide_no,
                sheet_name=item.sheet_name,
                cell_anchor=item.cell_anchor,
                section_path=item.section_path,
                ordinal_in_group=item.ordinal_in_group,
                status="ready",
            )
        )


async def _supersede_previous(
    session: AsyncSession,
    *,
    tenant_id: str,
    document: KnowledgeDocument,
    version_id: str,
    dispatcher: TaskDispatcher | None,
) -> None:
    old_version_ids = tuple(
        await session.scalars(
            select(KnowledgeDocumentVersion.id).where(
                KnowledgeDocumentVersion.tenant_id == tenant_id,
                KnowledgeDocumentVersion.document_id == document.id,
                KnowledgeDocumentVersion.id != version_id,
                KnowledgeDocumentVersion.status == "published",
            )
        )
    )
    await session.execute(
        update(KnowledgeDocumentVersion)
        .where(
            KnowledgeDocumentVersion.tenant_id == tenant_id,
            KnowledgeDocumentVersion.document_id == document.id,
            KnowledgeDocumentVersion.id != version_id,
            KnowledgeDocumentVersion.status == "published",
        )
        .values(status="superseded")
    )
    for old_id in old_version_ids:
        await enqueue_vector_job(session, tenant_id, old_id, "delete", dispatcher=dispatcher)
