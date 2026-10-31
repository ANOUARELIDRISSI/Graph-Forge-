from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


class PageRecord(BaseModel):
    url: str
    canonical_url: str | None = None
    title: str = ""
    text: str = ""
    language: str = "other"
    country_context: Literal["Morocco"] = "Morocco"
    source_domain: str
    document_type: Literal["html", "pdf", "rss"] = "html"
    source_feed_url: str | None = None
    published_at: datetime | None = None
    crawled_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TextChunk(BaseModel):
    id: str
    document_id: str
    index: int
    text: str
    source_url: str
    language: str


class ExtractedEntity(BaseModel):
    name: str
    entity_type: str
    confidence: float = 0.0


class ExtractedRelation(BaseModel):
    subject: str
    predicate: str
    object: str
    confidence: float = 0.0


class ExtractionResult(BaseModel):
    entities: list[ExtractedEntity] = Field(default_factory=list)
    relations: list[ExtractedRelation] = Field(default_factory=list)
    source_chunk_id: str
    # Provenance: which extractor produced this result ("heuristic",
    # "nvidia-llm" or "heuristic-fallback" when the remote call failed).
    method: str = "heuristic"


class GraphNode(BaseModel):
    id: str
    label: str
    name: str
    properties: dict[str, str | int | float] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    source: str
    relation: str
    target: str
    properties: dict[str, str | int | float] = Field(default_factory=dict)


class GraphSnapshot(BaseModel):
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)


class QuestionRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)


class Evidence(BaseModel):
    """A retrieved passage plus the provenance needed to verify an answer."""

    chunk_id: str
    url: str
    snippet: str
    score: float
    language: str = "other"


class AnswerResponse(BaseModel):
    answer: str
    sources: list[str]
    mode: str
    evidence: list[Evidence] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    subgraph: GraphSnapshot | None = None
    latency_ms: float = 0.0
    grounded: bool = False
