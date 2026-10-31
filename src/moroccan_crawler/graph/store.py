from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

from moroccan_crawler.ai import Extractor, heuristic_extract
from moroccan_crawler.chunking import chunk_page
from moroccan_crawler.domain.models import (
    ExtractionResult,
    GraphEdge,
    GraphNode,
    GraphSnapshot,
    PageRecord,
)
from moroccan_crawler.graph.resolution import resolve

_RELATION_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("publish", "publie", "release", "issue", "produce"), "PUBLISHES"),
    (("locat", "operat", "based", "situe", "region", "headquarter"), "OPERATES_IN"),
    (("regulat", "supervis", "oversee", "controle"), "REGULATES"),
    (("financ", "invest", "fund", "soutien"), "FINANCES"),
    (("employ", "emploi", "workforce"), "EMPLOYS"),
    (("partner", "collabor", "cooper", "partenaire"), "PARTNERS_WITH"),
    (("sector", "secteur", "industry", "industrie", "activity"), "BELONGS_TO_SECTOR"),
    (("export", "import", "trade", "supply", "commerce"), "TRADES_WITH"),
    (("own", "subsidi", "possede", "filiale"), "OWNS"),
    (("report", "statistic", "data", "indicateur", "rapport"), "REPORTS_ON"),
)


def canonical_relation(predicate: str) -> str:
    """Map unconstrained multilingual LLM predicates to a stable graph schema."""
    folded = unicodedata.normalize("NFKD", predicate.casefold()).encode("ascii", "ignore").decode()
    folded = re.sub(r"[^a-z0-9]+", "_", folded).strip("_")
    for terms, relation in _RELATION_RULES:
        if any(term in folded for term in terms):
            return relation
    return "RELATED_TO"


class GraphStore:
    """In-memory knowledge graph adapter with entity resolution.

    Extraction is pluggable: the NVIDIA/LLM extractor can be injected, while the
    deterministic heuristics keep tests and offline runs dependency-free.
    """

    def __init__(self, extractor: Extractor | None = None) -> None:
        self._nodes: dict[str, GraphNode] = {}
        self._edges: list[GraphEdge] = []
        self._extractor: Extractor = extractor or heuristic_extract
        self.extraction_methods: dict[str, int] = {}

    def ingest_pages(self, pages: Iterable[PageRecord]) -> None:
        for page in pages:
            source_id = f"source:{page.source_domain}"
            self._nodes[source_id] = GraphNode(
                id=source_id,
                label="Source",
                name=page.source_domain,
                properties={"country_context": page.country_context},
            )
            page_id = f"page:{page.url}"
            self._nodes[page_id] = GraphNode(
                id=page_id,
                label="Page",
                name=page.title or str(page.url),
                properties={
                    "language": page.language,
                    "url": str(page.canonical_url or page.url),
                    "document_type": page.document_type,
                },
            )
            self._add_edge(page_id, "PUBLISHED_BY", source_id)
            for chunk in chunk_page(page):
                result = self._extractor(chunk)
                self.extraction_methods[result.method] = (
                    self.extraction_methods.get(result.method, 0) + 1
                )
                self._ingest_extraction(page_id, source_id, result)

    def _ingest_extraction(self, page_id: str, source_id: str, result: ExtractionResult) -> None:
        entity_types = {entity.name.casefold(): entity.entity_type for entity in result.entities}
        for entity in result.entities:
            resolved = resolve(entity.name, entity.entity_type)
            existing = self._nodes.get(resolved.id)
            if existing is None:
                self._nodes[resolved.id] = GraphNode(
                    id=resolved.id,
                    label=resolved.entity_type,
                    name=resolved.name,
                    properties={
                        "mentions": 1,
                        "confidence": round(entity.confidence, 3),
                        "extraction": result.method,
                        "chunk": result.source_chunk_id,
                    },
                )
            else:
                existing.properties["mentions"] = int(existing.properties.get("mentions", 0)) + 1
            self._add_edge(page_id, "MENTIONS", resolved.id)
            # Direct source coverage makes source-level analytics cheap in Cypher.
            self._add_edge(source_id, "COVERS", resolved.id)
        for relation in result.relations:
            subject = resolve(
                relation.subject, entity_types.get(relation.subject.casefold(), "Entity")
            )
            obj = resolve(relation.object, entity_types.get(relation.object.casefold(), "Entity"))
            for resolved in (subject, obj):
                self._nodes.setdefault(
                    resolved.id,
                    GraphNode(id=resolved.id, label=resolved.entity_type, name=resolved.name),
                )
            canonical = canonical_relation(relation.predicate)
            edge = GraphEdge(
                source=subject.id,
                relation=canonical,
                target=obj.id,
                properties={
                    "chunk": result.source_chunk_id,
                    "source_page": page_id,
                    "confidence": relation.confidence,
                    "extraction": result.method,
                    "raw_predicate": relation.predicate[:200],
                },
            )
            if edge not in self._edges:
                self._edges.append(edge)

    def snapshot(self) -> GraphSnapshot:
        return GraphSnapshot(nodes=list(self._nodes.values()), edges=self._edges)

    def _add_edge(self, source: str, relation: str, target: str) -> None:
        edge = GraphEdge(source=source, relation=relation, target=target)
        if edge not in self._edges:
            self._edges.append(edge)
