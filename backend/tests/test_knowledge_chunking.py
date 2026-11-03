from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.modules.knowledge.chunking import split_content
from app.modules.knowledge.schemas import KnowledgeSpaceChunkingUpdateRequest


def test_chunking_prefers_a_paragraph_boundary_and_keeps_overlap_bounded() -> None:
    content = f"{'A' * 550}\n\n{'B' * 550}\n\n{'C' * 550}"

    chunks = split_content(content, chunk_size_chars=700, chunk_overlap_chars=100)

    assert len(chunks) == 3
    assert all(len(chunk) <= 700 for chunk in chunks)
    assert chunks[1].startswith("A" * 100)
    assert chunks[2].startswith("B" * 100)


def test_chunking_settings_reject_an_overlap_as_large_as_its_chunk() -> None:
    with pytest.raises(ValidationError, match="chunk_overlap_chars"):
        KnowledgeSpaceChunkingUpdateRequest(chunk_size_chars=500, chunk_overlap_chars=500)


def test_chunking_uses_a_custom_separator_as_a_paragraph_boundary() -> None:
    content = f"{'A' * 550}***{'B' * 550}***{'C' * 550}"

    chunks = split_content(
        content,
        chunk_size_chars=700,
        chunk_overlap_chars=100,
        chunk_separator="***",
    )

    assert len(chunks) == 3
    assert all("***" not in chunk for chunk in chunks)
    assert chunks[1].startswith("A" * 100)


def test_chunking_settings_reject_an_unsupported_separator_escape() -> None:
    with pytest.raises(ValidationError, match="chunk_separator contains an unsupported escape"):
        KnowledgeSpaceChunkingUpdateRequest(chunk_separator=r"\x")
