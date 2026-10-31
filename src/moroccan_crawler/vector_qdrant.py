from __future__ import annotations

import re
import uuid

from moroccan_crawler.ai import NvidiaClient
from moroccan_crawler.config import Settings
from moroccan_crawler.domain.models import TextChunk


class QdrantVectorStore:
    """Production vector store backed by Qdrant, with chunk provenance in payloads."""

    def __init__(
        self,
        settings: Settings | None = None,
        client: NvidiaClient | None = None,
        generation: str | None = None,
    ) -> None:
        from qdrant_client import QdrantClient

        self.settings = settings or Settings()
        self.embedder = client or NvidiaClient(self.settings)
        self.client = QdrantClient(url=self.settings.qdrant_url)
        self.collection = self.settings.qdrant_collection
        self.generation = generation or uuid.uuid4().hex
        self._chunks: list[TextChunk] = []

    def ensure_collection(self, dimensions: int) -> None:
        from qdrant_client.models import Distance, VectorParams

        if not self.client.collection_exists(self.collection):
            self.client.create_collection(
                self.collection,
                vectors_config=VectorParams(size=dimensions, distance=Distance.COSINE),
            )

    def add(self, chunks: list[TextChunk]) -> None:
        from qdrant_client.models import PointStruct

        if not chunks:
            return
        self._chunks = list(chunks)
        for start in range(0, len(chunks), 16):
            batch = chunks[start : start + 16]
            vectors = self.embedder.embed([chunk.text for chunk in batch])
            if len(vectors) != len(batch):
                raise ValueError("Embedding provider returned an incomplete batch")
            self.ensure_collection(len(vectors[0]))
            self.client.upsert(
                collection_name=self.collection,
                points=[
                    PointStruct(
                        id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{self.generation}:{chunk.id}")),
                        vector=vector,
                        payload={
                            **chunk.model_dump(mode="json"),
                            "generation": self.generation,
                        },
                    )
                    for chunk, vector in zip(batch, vectors, strict=True)
                ],
            )

    def search_scored(self, query: str, limit: int = 5) -> list[tuple[TextChunk, float]]:
        """Return ``(chunk, score)`` pairs, semantic cosine first.

        Qdrant's cosine score is kept as the primary signal; lexical overlap only
        contributes extra candidates and cannot override a clear semantic gap.
        """
        from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue

        if not self._chunks:
            return []
        vector = self.embedder.embed([query], input_type="query")[0]
        results = self.client.query_points(
            collection_name=self.collection,
            query=vector,
            limit=limit,
            query_filter=Filter(
                must=[
                    FieldCondition(
                        key="document_id",
                        match=MatchAny(any=list({chunk.document_id for chunk in self._chunks})),
                    ),
                    FieldCondition(key="generation", match=MatchValue(value=self.generation)),
                ]
            ),
        ).points
        terms = set(re.findall(r"\w+", query.casefold(), re.UNICODE))
        scored: dict[str, tuple[TextChunk, float]] = {}
        for result in results:
            if not result.payload:
                continue
            chunk = TextChunk.model_validate(result.payload)
            scored[chunk.id] = (chunk, float(result.score))
        for chunk in self._chunks:
            if chunk.id in scored:
                continue
            overlap = len(terms & set(re.findall(r"\w+", chunk.text.casefold(), re.UNICODE)))
            if overlap:
                scored[chunk.id] = (chunk, overlap / (len(terms) or 1))
        ranked = sorted(scored.values(), key=lambda item: item[1], reverse=True)
        return ranked[:limit]

    def search(self, query: str, limit: int = 5) -> list[TextChunk]:
        return [chunk for chunk, _ in self.search_scored(query, limit)]

    def count(self) -> int:
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        result = self.client.count(
            collection_name=self.collection,
            count_filter=Filter(
                must=[FieldCondition(key="generation", match=MatchValue(value=self.generation))]
            ),
            exact=True,
        )
        return int(result.count)
