from __future__ import annotations

import math
import re
from collections import Counter

from moroccan_crawler.ai import NvidiaClient
from moroccan_crawler.domain.models import TextChunk


class VectorStore:
    """Dependency-free cosine index; replaceable with pgvector/Qdrant later."""

    def __init__(self, client: NvidiaClient | None = None) -> None:
        self.client = client or NvidiaClient()
        self._rows: list[tuple[TextChunk, list[float]]] = []
        self._terms: dict[str, Counter] = {}
        self._df: Counter = Counter()
        self._average_length = 1.0

    def add(self, chunks: list[TextChunk]) -> None:
        self._rows = []
        for start in range(0, len(chunks), 16):
            batch = chunks[start : start + 16]
            self._rows.extend(
                zip(batch, self.client.embed([chunk.text for chunk in batch]), strict=True)
            )
        self._terms = {
            chunk.id: Counter(re.findall(r"\w+", chunk.text.casefold())) for chunk in chunks
        }
        self._df = Counter(term for tokens in self._terms.values() for term in tokens)
        self._average_length = sum(sum(tokens.values()) for tokens in self._terms.values()) / max(
            len(chunks), 1
        )

    def search_scored(self, query: str, limit: int = 5) -> list[tuple[TextChunk, float]]:
        """Return ``(chunk, score)`` pairs; the score is cosine similarity plus BM25.

        Exposing the score lets callers re-rank without discarding the semantic
        signal they would otherwise lose by re-sorting on lexical overlap alone.
        """
        if not self._rows:
            return []
        query_vector = self.client.embed([query], input_type="query")[0]
        scored = [
            (chunk, self._cosine(query_vector, vector) + self._bm25(query, chunk))
            for chunk, vector in self._rows
        ]
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:limit]

    def search(self, query: str, limit: int = 5) -> list[TextChunk]:
        return [chunk for chunk, _ in self.search_scored(query, limit)]

    def _bm25(self, query: str, chunk: TextChunk) -> float:
        """BM25 with corpus document frequency and document-length normalization."""
        tokens = self._terms[chunk.id]
        score = 0.0
        for term in set(re.findall(r"\w+", query.casefold())):
            frequency = tokens[term]
            document_frequency = self._df[term]
            inverse_frequency = math.log(
                1 + (len(self._rows) - document_frequency + 0.5) / (document_frequency + 0.5)
            )
            denominator = frequency + 1.2 * (
                0.25 + 0.75 * sum(tokens.values()) / max(self._average_length, 1)
            )
            score += inverse_frequency * frequency * 2.2 / denominator
        return score

    @staticmethod
    def _cosine(left: list[float], right: list[float]) -> float:
        return sum(a * b for a, b in zip(left, right)) / (
            (math.sqrt(sum(a * a for a in left)) or 1) * (math.sqrt(sum(b * b for b in right)) or 1)
        )


def deterministic_embedding(text: str) -> list[float]:
    from moroccan_crawler.ai import deterministic_embedding as embed

    return embed(text)
