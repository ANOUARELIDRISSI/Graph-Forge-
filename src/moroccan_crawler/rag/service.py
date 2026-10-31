from __future__ import annotations

import re
import time

from moroccan_crawler.ai import NvidiaClient
from moroccan_crawler.domain.models import (
    AnswerResponse,
    Evidence,
    GraphNode,
    GraphSnapshot,
    TextChunk,
)
from moroccan_crawler.graph.analytics import degree_centrality, neighborhood
from moroccan_crawler.observability import observe_generation
from moroccan_crawler.vector_store import VectorStore

_STOPWORDS = {
    "the",
    "a",
    "an",
    "of",
    "in",
    "on",
    "for",
    "and",
    "or",
    "to",
    "is",
    "are",
    "what",
    "which",
    "who",
    "how",
    "does",
    "do",
    "list",
    "show",
    "me",
    "about",
    "le",
    "la",
    "les",
    "des",
    "du",
    "de",
    "et",
    "un",
    "une",
    "que",
    "qui",
    "quel",
    "quels",
    "quelle",
    "quelles",
    "est",
    "sont",
    "dans",
    "sur",
    "pour",
}


class RagService:
    """Graph-aware GraphRAG: graph retrieval first, then grounded generation.

    The retriever combines three signals so answers stay explainable:
    1. graph seed matching (question terms resolve to entity nodes),
    2. a k-hop subgraph that supplies relational context,
    3. hybrid vector/lexical passage retrieval that supplies provenance.
    """

    def __init__(
        self,
        graph: GraphSnapshot,
        vector_store: VectorStore | None = None,
        client: NvidiaClient | None = None,
        hops: int = 2,
    ) -> None:
        self.graph = graph
        self.vector_store = vector_store
        self.client = client or NvidiaClient()
        self.hops = hops

    def answer(self, question: str) -> AnswerResponse:
        started = time.perf_counter()
        seeds = self._seed_nodes(question)
        subgraph = (
            neighborhood(self.graph, {node.id for node in seeds}, hops=self.hops)
            if seeds
            else GraphSnapshot()
        )
        retrieved = self.vector_store.search_scored(question, limit=20) if self.vector_store else []
        graph_urls = self._page_urls(subgraph)
        ranked = self._rank(question, retrieved, graph_urls)
        # Reserve evidence slots for different documents, then fill any spare
        # slots with additional passages. Near-duplicate chunks must not occupy
        # the entire context budget.
        diverse = []
        seen_urls = set()
        for chunk, _ in ranked:
            if chunk.source_url not in seen_urls:
                diverse.append(chunk)
                seen_urls.add(chunk.source_url)
        kept = {chunk.id for chunk in diverse}
        ordered = diverse + [chunk for chunk, _ in ranked if chunk.id not in kept]
        final = ordered[:5]
        scores = {chunk.id: score for chunk, score in ranked}
        evidence = [
            Evidence(
                chunk_id=chunk.id,
                url=str(chunk.source_url),
                snippet=chunk.text[:280],
                score=round(scores.get(chunk.id, 0.0), 4),
                language=chunk.language,
            )
            for chunk in final
        ]
        sources = list(dict.fromkeys(item.url for item in evidence))
        context = self._build_context(subgraph, evidence)
        with observe_generation(
            "moroccan-rag-answer",
            self.client.settings.nvidia_model,
            {
                "question": question,
                "context": context,
                "entities": [node.name for node in seeds],
                "subgraph_nodes": len(subgraph.nodes),
            },
        ) as generation:
            generated = self.client.generate(question, context)
            if generation is not None:
                generation.update(output=generated or "local-fallback")
        answer = generated or self._grounded_summary(question, seeds, subgraph, evidence)
        return AnswerResponse(
            answer=answer,
            sources=sources,
            mode="nvidia-graphrag" if generated else "local-baseline",
            evidence=evidence,
            entities=[node.name for node in seeds],
            subgraph=subgraph if subgraph.nodes else None,
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
            grounded=bool(evidence),
        )

    def _seed_nodes(self, question: str) -> list[GraphNode]:
        terms = {
            term
            for term in re.findall(r"[\w-]+", question.casefold(), re.UNICODE)
            if term not in _STOPWORDS and len(term) > 2
        }
        if not terms:
            return []
        degree = degree_centrality(self.graph)
        matches: list[GraphNode] = []
        for node in self.graph.nodes:
            if node.label in {"Page", "Source"}:
                continue
            name_terms = set(re.findall(r"[\w-]+", node.name.casefold(), re.UNICODE))
            if terms & name_terms:
                matches.append(node)
        matches.sort(
            key=lambda node: (
                degree.get(node.id, 0),
                int(node.properties.get("mentions", 0)),
            ),
            reverse=True,
        )
        return matches[:5]

    @staticmethod
    def _page_urls(subgraph: GraphSnapshot) -> set[str]:
        return {
            str(node.properties["url"])
            for node in subgraph.nodes
            if node.label == "Page" and "url" in node.properties
        }

    @staticmethod
    def _terms(text: str) -> set[str]:
        return {
            term
            for term in re.findall(r"[\w-]+", text.casefold(), re.UNICODE)
            if term not in _STOPWORDS and len(term) > 2
        }

    @classmethod
    def _rank(
        cls,
        question: str,
        scored: list[tuple[TextChunk, float]],
        graph_urls: set[str],
    ) -> list[tuple[TextChunk, float]]:
        """Blend retrieval signals without letting graph proximity dominate.

        The vector score is min-max normalised and given the largest weight so the
        semantic ordering survives re-ranking. Lexical overlap and graph proximity
        are bounded tie-breakers: a weak graph match can shift near-equal passages
        but cannot promote a passage the retriever scored well below a competitor.
        """
        if not scored:
            return []
        values = [score for _, score in scored]
        low, high = min(values), max(values)
        span = (high - low) or 1.0
        query_terms = cls._terms(question)
        ranked: list[tuple[TextChunk, float]] = []
        for chunk, score in scored:
            semantic = (score - low) / span
            chunk_terms = cls._terms(chunk.text)
            lexical = len(query_terms & chunk_terms) / (len(query_terms) or 1)
            proximity = 1.0 if str(chunk.source_url) in graph_urls else 0.0
            ranked.append((chunk, round(0.5 * semantic + 0.3 * lexical + 0.2 * proximity, 4)))
        ranked.sort(key=lambda item: item[1], reverse=True)
        return ranked

    @staticmethod
    def _build_context(subgraph: GraphSnapshot, evidence: list[Evidence]) -> str:
        by_id = {node.id: node.name for node in subgraph.nodes}
        triples = [
            f"{by_id.get(edge.source, edge.source)} -[{edge.relation}]-> "
            f"{by_id.get(edge.target, edge.target)}"
            for edge in subgraph.edges[:40]
        ]
        passages = [f"[{item.url}] {item.snippet}" for item in evidence]
        return (
            "Graph context:\n"
            + ("\n".join(triples) or "(no matching subgraph)")
            + "\n\nRetrieved passages:\n"
            + ("\n".join(passages) or "(no retrieved passages)")
        )

    @staticmethod
    def _grounded_summary(
        question: str,
        seeds: list[GraphNode],
        subgraph: GraphSnapshot,
        evidence: list[Evidence],
    ) -> str:
        entity_names = ", ".join(node.name for node in seeds) or "no matching entities"
        neighbour_names = (
            ", ".join(node.name for node in subgraph.nodes if node.label not in {"Page", "Source"})
            or "no linked entities"
        )
        if evidence:
            return (
                f"Question: {question}\n\n"
                f"Matched graph entities: {entity_names}.\n"
                f"Related entities in the {len(subgraph.nodes)}-node neighbourhood: {neighbour_names}.\n"
                f"Supporting evidence was retrieved from {len(evidence)} passage(s): "
                + "; ".join(item.url for item in evidence[:3])
                + ".\n\n"
                "Enable NVIDIA remote AI (NVIDIA_ENABLE_REMOTE_AI=true) for a generated summary."
            )
        return (
            f"Question: {question}\n\n"
            f"Matched graph entities: {entity_names}.\n"
            "No passage evidence was retrieved, so this answer is limited to the graph structure. "
            "Build the vector index to add citations."
        )
