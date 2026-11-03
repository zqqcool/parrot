from __future__ import annotations

DEFAULT_CHUNK_OVERLAP_CHARS = 200
DEFAULT_CHUNK_SEPARATOR = r"\n\n"
DEFAULT_CHUNK_SIZE_CHARS = 4_000
MAX_CHUNK_SIZE_CHARS = 12_000
MIN_CHUNK_SIZE_CHARS = 500


def split_content(
    content: str,
    chunk_size_chars: int,
    chunk_overlap_chars: int,
    chunk_separator: str = DEFAULT_CHUNK_SEPARATOR,
) -> tuple[str, ...]:
    """Split normalized text near paragraph boundaries with a bounded overlap."""
    _validate(chunk_size_chars, chunk_overlap_chars)
    separator = decode_chunk_separator(chunk_separator)
    text = _normalize_separator(content.strip(), separator)
    if not text:
        return ()
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = _boundary(text, start, chunk_size_chars)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(start + 1, end - chunk_overlap_chars)
    return tuple(chunks)


def decode_chunk_separator(value: str) -> str:
    """Decode the narrow escape syntax exposed by the management API."""
    if not value:
        raise ValueError("chunk_separator is required")
    decoded: list[str] = []
    index = 0
    escapes = {"n": "\n", "r": "\r", "t": "\t", "\\": "\\"}
    while index < len(value):
        character = value[index]
        if character != "\\":
            decoded.append(character)
            index += 1
            continue
        if index + 1 >= len(value) or value[index + 1] not in escapes:
            raise ValueError("chunk_separator contains an unsupported escape")
        decoded.append(escapes[value[index + 1]])
        index += 2
    result = "".join(decoded)
    if not result:
        raise ValueError("chunk_separator is required")
    return result


def _normalize_separator(content: str, separator: str) -> str:
    if separator == "\n\n":
        return content
    return content.replace(separator, "\n\n")


def _boundary(text: str, start: int, chunk_size_chars: int) -> int:
    end = min(start + chunk_size_chars, len(text))
    if end == len(text):
        return end
    minimum = start + chunk_size_chars // 2
    paragraph = text.rfind("\n\n", minimum, end + 1)
    if paragraph > start:
        return paragraph
    line = text.rfind("\n", minimum, end + 1)
    if line > start:
        return line
    word = text.rfind(" ", minimum, end + 1)
    return word if word > start else end


def _validate(chunk_size_chars: int, chunk_overlap_chars: int) -> None:
    if not MIN_CHUNK_SIZE_CHARS <= chunk_size_chars <= MAX_CHUNK_SIZE_CHARS:
        raise ValueError("chunk_size_chars is outside the supported range")
    if not 0 <= chunk_overlap_chars < chunk_size_chars:
        raise ValueError("chunk_overlap_chars must be smaller than chunk_size_chars")
