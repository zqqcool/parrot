from __future__ import annotations

import pytest

from app.modules.knowledge.preprocessing import KnowledgeTextProcessingError, process_content


def test_whitespace_normalization_preserves_paragraph_boundaries() -> None:
    processed = process_content(
        "Title  \t\r\n\r\n\r\nParagraph\t  text  ",
        normalize_whitespace=True,
        remove_urls_and_emails=False,
    )

    assert processed == "Title\n\nParagraph text"


def test_url_and_email_removal_is_applied_before_whitespace_normalization() -> None:
    processed = process_content(
        "Contact alice@example.test or https://docs.example.test/release for details.",
        normalize_whitespace=True,
        remove_urls_and_emails=True,
    )

    assert processed == "Contact or for details."


def test_disabled_rules_keep_existing_canonical_text_behavior() -> None:
    processed = process_content(
        "  Release\tpolicy  \r\n\r\nhttps://docs.example.test  ",
        normalize_whitespace=False,
        remove_urls_and_emails=False,
    )

    assert processed == "Release\tpolicy\n\nhttps://docs.example.test"


def test_removal_that_leaves_no_text_is_rejected() -> None:
    with pytest.raises(KnowledgeTextProcessingError, match="EMPTY_AFTER_PROCESSING"):
        process_content(
            " https://docs.example.test  alice@example.test ",
            normalize_whitespace=True,
            remove_urls_and_emails=True,
        )
