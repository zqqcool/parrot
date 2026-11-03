from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Protocol, cast

from app.modules.agent_runtime.contracts import ChatMessage
from app.modules.knowledge.runtime_types import KnowledgeEvidenceItem, KnowledgeMediaRef

_CITE_MARKER = re.compile(
    r"(?:【cite:((?:knowledge_chunk_)?[A-Za-z0-9_-]+)】|"
    r"\[\^cite:((?:knowledge_chunk_)?[A-Za-z0-9_-]+)\])"
)
_ANGLE_CHUNK = re.compile(r"<knowledge_chunk_[A-Za-z0-9_-]+>")
_BARE_CHUNK = re.compile(r"\bknowledge_chunk_[A-Za-z0-9_-]+\b")
_SOURCES_SECTION = re.compile(
    r"(?:\n{1,2}|^)(?:信息来源|参考来源|Sources?)\s*[:：][^\n]*"
    r"(?:\n+[^\S\n]*<?knowledge_chunk_[^>\n\s]+>?)*"
    r"|(?:\n{1,2}|^)(?:信息来源|参考来源|Sources?)\s*[:：][^\n]*"
    r"(?:\n*[、,，\s]*【cite:[^】]+】)*",
    re.IGNORECASE,
)
_TRAILING_CITE_LINE = re.compile(
    r"(?:\n|^)[ \t]*(?:【cite:[^】]+】[、,，\s]*)+【cite:[^】]+】[ \t]*$"
)


@dataclass(frozen=True)
class KnowledgeCitationInventoryItem:
    citation_id: str
    title: str
    anchor: str
    slide_no: int | None
    space_id: str
    has_media: bool
    primary_media_kind: str | None
    primary_asset_id: str | None
    primary_alt: str | None


@dataclass(frozen=True)
class AssembledKnowledgeOutput:
    content: str
    citations: tuple[dict[str, object], ...]
    media: tuple[dict[str, object], ...]


class CitationInventoryHydratorPort(Protocol):
    async def hydrate(
        self, tenant_id: str, citation_ids: tuple[str, ...]
    ) -> tuple[KnowledgeCitationInventoryItem, ...]: ...


def inventory_from_evidence(
    items: tuple[KnowledgeEvidenceItem, ...],
) -> tuple[KnowledgeCitationInventoryItem, ...]:
    return tuple(_inventory_item(item) for item in items)


def catalog_for_model(
    inventory: tuple[KnowledgeCitationInventoryItem, ...],
) -> list[dict[str, object]]:
    return [
        {
            "citation_id": item.citation_id,
            "title": item.title,
            "anchor": item.anchor,
            "slide_no": item.slide_no,
            "space_id": item.space_id,
            "has_media": item.has_media,
            "primary_media_kind": item.primary_media_kind,
        }
        for item in inventory
    ]


def inventory_from_tool_result(
    result: dict[str, object],
) -> tuple[KnowledgeCitationInventoryItem, ...]:
    catalog = result.get("citations")
    attachments = result.get("_attachment_media")
    asset_by_citation: dict[str, dict[str, object]] = {}
    if isinstance(attachments, list):
        for raw in cast(list[object], attachments):
            if not isinstance(raw, dict):
                continue
            typed_row = cast(dict[str, object], raw)
            citation_id = typed_row.get("citation_id")
            if isinstance(citation_id, str):
                asset_by_citation[citation_id] = typed_row
    if not isinstance(catalog, list):
        return ()
    items: list[KnowledgeCitationInventoryItem] = []
    for raw in cast(list[object], catalog):
        if not isinstance(raw, dict):
            continue
        typed_row = cast(dict[str, object], raw)
        citation_id = typed_row.get("citation_id")
        title = typed_row.get("title")
        anchor = typed_row.get("anchor")
        space_id = typed_row.get("space_id")
        if not (
            isinstance(citation_id, str)
            and citation_id
            and isinstance(title, str)
            and title
            and isinstance(anchor, str)
            and anchor
            and isinstance(space_id, str)
            and space_id
        ):
            continue
        attachment = asset_by_citation.get(citation_id, {})
        slide_no = typed_row.get("slide_no")
        kind = typed_row.get("primary_media_kind")
        asset_id = attachment.get("asset_id")
        alt = attachment.get("alt")
        items.append(
            KnowledgeCitationInventoryItem(
                citation_id=citation_id,
                title=title,
                anchor=anchor,
                slide_no=slide_no if isinstance(slide_no, int) else None,
                space_id=space_id,
                has_media=bool(typed_row.get("has_media")),
                primary_media_kind=kind if isinstance(kind, str) else None,
                primary_asset_id=asset_id if isinstance(asset_id, str) else None,
                primary_alt=alt if isinstance(alt, str) else None,
            )
        )
    return tuple(items)


def inventory_from_messages(
    messages: list[ChatMessage] | tuple[ChatMessage, ...],
) -> tuple[KnowledgeCitationInventoryItem, ...]:
    merged: dict[str, KnowledgeCitationInventoryItem] = {}
    for message in messages:
        if message.role != "tool" or message.name != "knowledge_search" or not message.content:
            continue
        try:
            payload = json.loads(message.content)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        for item in inventory_from_tool_result(cast(dict[str, object], payload)):
            merged.setdefault(item.citation_id, item)
    return tuple(merged.values())


def merge_inventories(
    *groups: tuple[KnowledgeCitationInventoryItem, ...],
) -> tuple[KnowledgeCitationInventoryItem, ...]:
    merged: dict[str, KnowledgeCitationInventoryItem] = {}
    for group in groups:
        for item in group:
            merged.setdefault(item.citation_id, item)
    return tuple(merged.values())


def attachment_media_for_result(
    inventory: tuple[KnowledgeCitationInventoryItem, ...],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for item in inventory:
        if item.primary_asset_id is None:
            continue
        rows.append(
            {
                "citation_id": item.citation_id,
                "asset_id": item.primary_asset_id,
                "kind": item.primary_media_kind or "slide_render",
                "role": "primary",
                "alt": item.primary_alt or item.title,
            }
        )
    return rows


def extract_citation_tokens(content: str) -> tuple[str, ...]:
    ordered: list[str] = []
    seen: set[str] = set()
    for match in _CITE_MARKER.finditer(content):
        token = match.group(1) or match.group(2)
        if token and token not in seen:
            seen.add(token)
            ordered.append(token)
    for match in _ANGLE_CHUNK.finditer(content):
        token = match.group(0).strip("<>")
        if token not in seen:
            seen.add(token)
            ordered.append(token)
    if not ordered:
        for match in _BARE_CHUNK.finditer(content):
            token = match.group(0)
            if token not in seen:
                seen.add(token)
                ordered.append(token)
    return tuple(ordered)


def assemble_knowledge_output(
    content: str,
    inventory: tuple[KnowledgeCitationInventoryItem, ...],
) -> AssembledKnowledgeOutput:
    cleaned = _sanitize_content(content)
    if not inventory:
        return AssembledKnowledgeOutput(content=cleaned, citations=(), media=())
    allowed = {item.citation_id: item for item in inventory}
    cited_tokens = extract_citation_tokens(content)
    selected_ids: list[str] = []
    seen: set[str] = set()
    for token in cited_tokens:
        resolved = _resolve_inventory_id(token, allowed)
        if resolved is not None and resolved not in seen:
            seen.add(resolved)
            selected_ids.append(resolved)
    if not selected_ids:
        selected_ids = [item.citation_id for item in inventory]
    citations = tuple(_public_citation(allowed[citation_id]) for citation_id in selected_ids)
    media = tuple(
        row
        for citation_id in selected_ids
        if (row := _public_media(allowed[citation_id])) is not None
    )
    return AssembledKnowledgeOutput(content=cleaned, citations=citations, media=media)


def completion_extra(assembled: AssembledKnowledgeOutput) -> dict[str, object]:
    extra: dict[str, object] = {}
    if assembled.citations:
        extra["citations"] = list(assembled.citations)
    if assembled.media:
        extra["media"] = list(assembled.media)
    return extra


def hydration_candidates(
    content: str, inventory: tuple[KnowledgeCitationInventoryItem, ...]
) -> tuple[str, ...]:
    known = {item.citation_id for item in inventory}
    tokens = extract_citation_tokens(content)
    missing: list[str] = []
    for token in tokens:
        if _resolve_inventory_id(token, {item.citation_id: item for item in inventory}) is not None:
            continue
        candidate = token if token.startswith("knowledge_chunk_") else f"knowledge_chunk_{token}"
        if candidate not in known and candidate not in missing:
            missing.append(candidate)
        if token not in known and token not in missing and token != candidate:
            missing.append(token)
    return tuple(missing)


def _inventory_item(item: KnowledgeEvidenceItem) -> KnowledgeCitationInventoryItem:
    primary = _primary_media(item.media_refs)
    return KnowledgeCitationInventoryItem(
        citation_id=item.citation_id,
        title=item.title,
        anchor=item.citation_anchor,
        slide_no=item.slide_no,
        space_id=item.space_id,
        has_media=primary is not None,
        primary_media_kind=None if primary is None else primary.asset_kind,
        primary_asset_id=None if primary is None else primary.asset_id,
        primary_alt=_media_alt(item, primary),
    )


def _primary_media(refs: tuple[KnowledgeMediaRef, ...]) -> KnowledgeMediaRef | None:
    if not refs:
        return None
    for kind in ("slide_render", "thumb", "embedded"):
        pool = tuple(ref for ref in refs if ref.asset_kind == kind)
        if pool:
            return min(pool, key=lambda ref: (ref.ordinal, ref.asset_id))
    return min(refs, key=lambda ref: (ref.ordinal, ref.asset_id))


def _media_alt(item: KnowledgeEvidenceItem, primary: KnowledgeMediaRef | None) -> str | None:
    if primary is None:
        return None
    if primary.slide_no is not None:
        return f"{item.title} · 第 {primary.slide_no} 页"
    if item.citation_anchor:
        return f"{item.title} · {item.citation_anchor}"
    return item.title


def _resolve_inventory_id(
    token: str, allowed: dict[str, KnowledgeCitationInventoryItem]
) -> str | None:
    if token in allowed:
        return token
    prefixed = token if token.startswith("knowledge_chunk_") else f"knowledge_chunk_{token}"
    if prefixed in allowed:
        return prefixed
    for citation_id in allowed:
        if citation_id.endswith(token) or citation_id.endswith(f"_{token}"):
            return citation_id
    return None


def _sanitize_content(content: str) -> str:
    cleaned = _SOURCES_SECTION.sub("", content)
    cleaned = _TRAILING_CITE_LINE.sub("", cleaned)
    cleaned = _ANGLE_CHUNK.sub("", cleaned)
    cleaned = _CITE_MARKER.sub("", cleaned)
    cleaned = re.sub(r"[、,，\s]*$", "", cleaned)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def _public_citation(item: KnowledgeCitationInventoryItem) -> dict[str, object]:
    return {
        "citation_id": item.citation_id,
        "title": item.title,
        "anchor": item.anchor,
        "slide_no": item.slide_no,
    }


def _public_media(item: KnowledgeCitationInventoryItem) -> dict[str, object] | None:
    if item.primary_asset_id is None:
        return None
    return {
        "citation_id": item.citation_id,
        "asset_id": item.primary_asset_id,
        "kind": item.primary_media_kind or "slide_render",
        "role": "primary",
        "alt": item.primary_alt or item.title,
    }
