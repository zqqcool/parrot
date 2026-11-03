from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol

KnowledgeMatchSource = Literal["lexical", "vector"]


@dataclass(frozen=True)
class KnowledgeRuntimeContext:
    tenant_id: str
    agent_id: str
    query: str
    limit: int = 6


@dataclass(frozen=True)
class KnowledgeRetrievalProvenance:
    retrieval_method: str
    embedding_config_name: str | None = None
    reranker_config_name: str | None = None
    degradation_reason: str | None = None


@dataclass(frozen=True)
class KnowledgeMediaRef:
    asset_id: str
    slide_no: int | None = None
    sheet_name: str | None = None
    cell_anchor: str | None = None
    section_path: str | None = None
    asset_kind: str = "slide_render"
    ordinal: int = 0


@dataclass(frozen=True)
class KnowledgeEvidenceItem:
    citation_id: str
    title: str
    citation_anchor: str
    space_id: str
    retrieval_method: str
    score: float
    excerpt: str
    document_id: str = ""
    document_version_id: str = ""
    content_chars: int = 0
    embedding_config_name: str | None = None
    reranker_config_name: str | None = None
    degradation_reason: str | None = None
    match_sources: tuple[KnowledgeMatchSource, ...] = ()
    vector_score: float | None = None
    slide_no: int | None = None
    group_id: str | None = None
    media_refs: tuple[KnowledgeMediaRef, ...] = ()


@dataclass(frozen=True)
class KnowledgeEvidenceBundle:
    content: str = ""
    citation_ids: tuple[str, ...] = ()
    items: tuple[KnowledgeEvidenceItem, ...] = ()
    status: str = "not_applicable"
    retrieval_method: str = "none"
    candidate_count: int = 0
    duration_ms: int = 0
    embed_duration_ms: int = 0
    space_count: int = 0
    degradation_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class KnowledgeCandidateSelection:
    ranked_ids: tuple[str, ...]
    scores: dict[str, float]
    retrieval_method: str
    provenance_by_space: dict[str, KnowledgeRetrievalProvenance]
    degradation_reasons: tuple[str, ...] = ()
    match_sources_by_chunk: dict[str, tuple[KnowledgeMatchSource, ...]] = field(
        default_factory=lambda: dict[str, tuple[KnowledgeMatchSource, ...]]()
    )
    vector_scores_by_chunk: dict[str, float] = field(default_factory=lambda: dict[str, float]())
    result_limit: int | None = None


class KnowledgeRuntimePort(Protocol):
    async def retrieve(self, context: KnowledgeRuntimeContext) -> KnowledgeEvidenceBundle: ...
