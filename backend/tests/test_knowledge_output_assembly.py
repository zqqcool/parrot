from __future__ import annotations

import json

import pytest

from app.modules.agent_runtime.knowledge_output import (
    KnowledgeCitationInventoryItem,
    assemble_knowledge_output,
    catalog_for_model,
    extract_citation_tokens,
    hydration_candidates,
    inventory_from_evidence,
)
from app.modules.agent_runtime.model_observation import tool_result_message
from app.modules.knowledge.runtime_types import KnowledgeEvidenceItem, KnowledgeMediaRef


def test_knowledge_search_observation_keeps_citation_catalog_without_private_media() -> None:
    inventory = (
        KnowledgeCitationInventoryItem(
            citation_id="knowledge_chunk_a",
            title="CRM手册",
            anchor="slide-4",
            slide_no=4,
            space_id="space_test",
            has_media=True,
            primary_media_kind="slide_render",
            primary_asset_id="media_a",
            primary_alt="CRM手册 · 第 4 页",
        ),
    )
    rendered = tool_result_message(
        {
            "status": "ok",
            "citations": catalog_for_model(inventory),
            "citation_ids": ["knowledge_chunk_a"],
            "evidence": "x" * 8_000,
            "_attachment_media": [
                {
                    "citation_id": "knowledge_chunk_a",
                    "asset_id": "media_a",
                    "kind": "slide_render",
                    "role": "primary",
                    "alt": "CRM手册 · 第 4 页",
                }
            ],
        }
    )
    payload = json.loads(rendered)
    assert payload["citations"][0]["citation_id"] == "knowledge_chunk_a"
    assert "_attachment_media" not in payload
    assert "media_a" not in rendered


def test_assemble_knowledge_output_resolves_abbreviated_cite_markers() -> None:
    inventory = (
        KnowledgeCitationInventoryItem(
            citation_id="knowledge_chunk_CkwHIHIhYh-L9aVzQ_1jE5ew",
            title="至尊宝APP操作手册",
            anchor="slide-5",
            slide_no=5,
            space_id="space_test",
            has_media=True,
            primary_media_kind="thumb",
            primary_asset_id="media_thumb",
            primary_alt="至尊宝APP操作手册 · 第 5 页",
        ),
    )
    assembled = assemble_knowledge_output(
        "登录步骤如下。\n"
        "【cite:CkwHIHIhYh-L9aVzQ_1jE5ew】、【cite:dg_50WL-YAk_9mmXnit0Lga0】",
        inventory,
    )
    assert "cite:" not in assembled.content
    assert assembled.content == "登录步骤如下。"
    assert [item["citation_id"] for item in assembled.citations] == [
        "knowledge_chunk_CkwHIHIhYh-L9aVzQ_1jE5ew"
    ]
    assert assembled.media[0]["asset_id"] == "media_thumb"


def test_hydration_candidates_include_abbreviated_tokens() -> None:
    tokens = extract_citation_tokens(
        "正文【cite:CkwHIHIhYh-L9aVzQ_1jE5ew】【cite:knowledge_chunk_other】"
    )
    assert tokens == ("CkwHIHIhYh-L9aVzQ_1jE5ew", "knowledge_chunk_other")
    missing = hydration_candidates("正文【cite:CkwHIHIhYh-L9aVzQ_1jE5ew】", ())
    assert "knowledge_chunk_CkwHIHIhYh-L9aVzQ_1jE5ew" in missing


def test_inventory_prefers_slide_render_then_thumb() -> None:
    item = KnowledgeEvidenceItem(
        citation_id="knowledge_chunk_a",
        title="CRM手册",
        citation_anchor="slide-4",
        space_id="space_test",
        retrieval_method="hybrid",
        score=1.0,
        excerpt="创建客户",
        slide_no=4,
        media_refs=(
            KnowledgeMediaRef(asset_id="thumb_a", asset_kind="thumb", ordinal=0, slide_no=4),
            KnowledgeMediaRef(
                asset_id="slide_a", asset_kind="slide_render", ordinal=1, slide_no=4
            ),
        ),
    )
    inventory = inventory_from_evidence((item,))
    assert inventory[0].primary_asset_id == "slide_a"
    assert inventory[0].primary_media_kind == "slide_render"


@pytest.mark.asyncio
async def test_session_hydrator_protocol_shape() -> None:
    class Stub:
        async def hydrate(
            self, tenant_id: str, citation_ids: tuple[str, ...]
        ) -> tuple[KnowledgeCitationInventoryItem, ...]:
            del tenant_id
            return tuple(
                KnowledgeCitationInventoryItem(
                    citation_id=citation_id,
                    title="手册",
                    anchor="slide-1",
                    slide_no=1,
                    space_id="space_test",
                    has_media=False,
                    primary_media_kind=None,
                    primary_asset_id=None,
                    primary_alt=None,
                )
                for citation_id in citation_ids
            )

    hydrated = await Stub().hydrate("tenant_test", ("knowledge_chunk_a",))
    assert hydrated[0].citation_id == "knowledge_chunk_a"
