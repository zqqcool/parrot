from __future__ import annotations

import re


class KnowledgeTextProcessingError(ValueError):
    pass


_EMAIL_PATTERN = re.compile(r"(?<![\w.+-])[\w.+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+(?![\w.-])")
_URL_PATTERN = re.compile(r"(?<![\w@])(?:https?://|www\.)[^\s<>\]\[(){}]+", re.IGNORECASE)
_HORIZONTAL_WHITESPACE = re.compile(r"[ \t]+")
_EXCESS_BLANK_LINES = re.compile(r"\n[ \t]*\n(?:[ \t]*\n)+")


def process_content(
    content: str,
    *,
    normalize_whitespace: bool,
    remove_urls_and_emails: bool,
) -> str:
    """Apply the versioned local text-processing profile before chunking."""
    processed = content.replace("\r\n", "\n").replace("\r", "\n")
    if remove_urls_and_emails:
        processed = _URL_PATTERN.sub(" ", processed)
        processed = _EMAIL_PATTERN.sub(" ", processed)
    if normalize_whitespace:
        processed = _normalize_whitespace(processed)
    else:
        processed = "\n".join(line.rstrip() for line in processed.split("\n")).strip()
    if not processed:
        raise KnowledgeTextProcessingError("KNOWLEDGE_DOCUMENT_EMPTY_AFTER_PROCESSING")
    return processed


def _normalize_whitespace(content: str) -> str:
    lines = (_HORIZONTAL_WHITESPACE.sub(" ", line).strip() for line in content.split("\n"))
    return _EXCESS_BLANK_LINES.sub("\n\n", "\n".join(lines)).strip()
