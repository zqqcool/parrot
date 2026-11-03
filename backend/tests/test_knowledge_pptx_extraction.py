from __future__ import annotations

import io
from typing import Any, cast

import pytest
from pptx import Presentation

from app.modules.knowledge.extraction import default_knowledge_extractor
from app.modules.knowledge.extraction.pptx import PptxDocumentExtractor
from app.modules.knowledge.extractor import KnowledgeExtractionError
from app.modules.knowledge.ingestion_validation import validate_uploaded_file


def _minimal_pptx(*, title: str = "1 User Login", body: str = "Click Sign in with SSO") -> bytes:
    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[1])
    cast(Any, slide.shapes.title).text = title
    cast(Any, slide.placeholders[1]).text = body
    buffer = io.BytesIO()
    presentation.save(buffer)
    return buffer.getvalue()


def test_plain_extractor_port_preserves_text_documents() -> None:
    extracted = default_knowledge_extractor().extract(
        b"Deployment policy\n\nStep one",
        "text/plain",
        max_chars=1_000,
        max_pdf_pages=10,
        max_slides=10,
    )
    assert extracted.format_profile == "plain_text"
    assert extracted.blocks[0].index_text == "Deployment policy\n\nStep one"
    assert extracted.slide_count == 0


def test_pptx_validation_accepts_ooxml_presentation() -> None:
    content = _minimal_pptx()
    item = validate_uploaded_file(
        content,
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "manual.pptx",
        5_000_000,
    )
    assert item.extension == ".pptx"


def test_pptx_extractor_builds_slide_blocks_and_chapter_groups() -> None:
    content = _minimal_pptx()
    # second slide same chapter title
    presentation = Presentation(io.BytesIO(content))
    slide = presentation.slides.add_slide(presentation.slide_layouts[1])
    cast(Any, slide.shapes.title).text = "1 User Login"
    cast(
        Any, slide.placeholders[1]
    ).text = "1-2 Login\nIn the pop-up window, click Sign in with SSO"
    buffer = io.BytesIO()
    presentation.save(buffer)
    content = buffer.getvalue()

    extracted = PptxDocumentExtractor().extract(
        content,
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        max_chars=50_000,
        max_pdf_pages=10,
        max_slides=50,
    )
    assert extracted.format_profile == "pptx"
    assert extracted.slide_count == 2
    assert len(extracted.blocks) == 2
    assert extracted.blocks[0].citation_anchor == "slide-1"
    assert extracted.blocks[1].step_label is not None
    assert len(extracted.groups) == 1
    assert extracted.groups[0].ordinal_start == 1
    assert extracted.groups[0].ordinal_end == 2
    assert "Sign in with SSO" in extracted.joined_index_text()


def test_pptx_slide_limit_is_enforced() -> None:
    content = _minimal_pptx()
    with pytest.raises(KnowledgeExtractionError, match="KNOWLEDGE_PPTX_SLIDE_LIMIT"):
        PptxDocumentExtractor().extract(
            content,
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            max_chars=50_000,
            max_pdf_pages=10,
            max_slides=0,
        )


def test_composite_routes_pptx() -> None:
    extracted = default_knowledge_extractor().extract(
        _minimal_pptx(),
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        max_chars=50_000,
        max_pdf_pages=10,
        max_slides=50,
    )
    assert extracted.extractor_name == "pptx_document"
