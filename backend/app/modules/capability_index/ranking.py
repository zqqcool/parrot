from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

_TOKEN = re.compile(r"[a-z0-9_]+|[\u4e00-\u9fff]", re.IGNORECASE)


@dataclass(frozen=True)
class CapabilitySearchDocument:
    source_id: str
    text: str


def bm25_rank(query: str, documents: tuple[CapabilitySearchDocument, ...]) -> tuple[str, ...]:
    terms = _tokens(query)
    if not terms or not documents:
        return ()
    tokenized = tuple(_tokens(item.text) for item in documents)
    average_length = sum(len(item) for item in tokenized) / len(tokenized)
    document_frequency = Counter(term for item in tokenized for term in set(item))
    scores: list[tuple[str, float, int]] = []
    for index, (document, terms_in_document) in enumerate(zip(documents, tokenized, strict=True)):
        frequencies = Counter(terms_in_document)
        score = sum(
            _term_score(
                term,
                frequencies[term],
                len(terms_in_document),
                average_length,
                document_frequency[term],
                len(documents),
            )
            for term in terms
            if frequencies[term]
        )
        if score > 0:
            scores.append((document.source_id, score, index))
    scores.sort(key=lambda item: (-item[1], item[2], item[0]))
    return tuple(item[0] for item in scores)


def rrf_rank(
    *rankings: tuple[str, ...], limit: int | None = 2, constant: int = 60
) -> tuple[str, ...]:
    scores: dict[str, float] = {}
    positions: dict[str, int] = {}
    for ranking in rankings:
        for index, source_id in enumerate(ranking, start=1):
            scores[source_id] = scores.get(source_id, 0) + 1 / (constant + index)
            positions[source_id] = min(positions.get(source_id, index), index)
    ranked = tuple(
        source_id
        for source_id, _ in sorted(
            scores.items(), key=lambda item: (-item[1], positions[item[0]], item[0])
        )
    )
    return ranked if limit is None else ranked[:limit]


def _tokens(value: str) -> tuple[str, ...]:
    return tuple(match.group(0).casefold() for match in _TOKEN.finditer(value))


def _term_score(
    term: str,
    frequency: int,
    length: int,
    average_length: float,
    document_frequency: int,
    total: int,
) -> float:
    inverse_frequency = math.log(
        1 + (total - document_frequency + 0.5) / (document_frequency + 0.5)
    )
    denominator = frequency + 1.2 * (1 - 0.75 + 0.75 * length / max(average_length, 1))
    return inverse_frequency * frequency * 2.2 / denominator
