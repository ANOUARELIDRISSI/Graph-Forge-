from moroccan_crawler.ai import NvidiaClient
from moroccan_crawler.config import Settings
from moroccan_crawler.domain.models import (
    GraphEdge,
    GraphNode,
    GraphSnapshot,
    PageRecord,
    TextChunk,
)
from moroccan_crawler.graph.store import GraphStore
from moroccan_crawler.rag.service import RagService


def test_page_becomes_graph_provenance() -> None:
    page = PageRecord(
        url="https://example.ma/a",
        title="Automotive",
        text="Automotive finance",
        source_domain="example.ma",
    )
    store = GraphStore()
    store.ingest_pages([page])
    snapshot = store.snapshot()
    assert any(node.label == "Source" and node.name == "example.ma" for node in snapshot.nodes)
    assert any(edge.relation == "MENTIONS" for edge in snapshot.edges)


def test_rag_baseline_returns_sources() -> None:
    page = PageRecord(
        url="https://example.ma/a", title="Business", text="Tourism", source_domain="example.ma"
    )
    store = GraphStore()
    store.ingest_pages([page])
    answer = RagService(
        store.snapshot(), client=NvidiaClient(Settings(nvidia_enable_remote_ai=False))
    ).answer("What sectors exist?")
    assert answer.mode == "local-baseline"
    assert answer.sources == []  # No retrieved evidence means no citations.


class _StubStore:
    """Minimal scored vector store used to isolate the re-ranking logic."""

    def __init__(self, scored: list[tuple[TextChunk, float]]) -> None:
        self._scored = scored

    def search_scored(self, query: str, limit: int = 20) -> list[tuple[TextChunk, float]]:
        return self._scored[:limit]


def _chunk(chunk_id: str, text: str, url: str) -> TextChunk:
    return TextChunk(
        id=chunk_id, document_id=url, index=0, text=text, source_url=url, language="fr"
    )


def test_graph_proximity_cannot_promote_a_weak_passage() -> None:
    """A semantically weak passage must not outrank a strong one just because
    its page appears in the retrieved subgraph."""
    strong = _chunk("strong", "tourism sector growth Morocco", "https://a.ma/1")
    weak = _chunk("weak", "cookie banner and navigation links", "https://b.ma/1")
    entity = GraphNode(id="sector:tourism", label="Sector", name="tourism")
    page = GraphNode(
        id="page:https://b.ma/1", label="Page", name="b", properties={"url": "https://b.ma/1"}
    )
    graph = GraphSnapshot(
        nodes=[entity, page],
        edges=[GraphEdge(source=page.id, relation="MENTIONS", target=entity.id)],
    )
    service = RagService(
        graph,
        vector_store=_StubStore([(strong, 0.9), (weak, 0.1)]),
        client=NvidiaClient(Settings(nvidia_enable_remote_ai=False)),
    )
    answer = service.answer("tourism sector")
    assert answer.evidence[0].chunk_id == "strong"
    assert answer.evidence[0].url == "https://a.ma/1"


def test_graph_proximity_breaks_a_semantic_tie() -> None:
    """When two passages are semantically equal, the in-subgraph one wins."""
    in_graph = _chunk("in_graph", "tourism sector overview", "https://b.ma/1")
    outside = _chunk("outside", "tourism sector overview", "https://c.ma/1")
    entity = GraphNode(id="sector:tourism", label="Sector", name="tourism")
    page = GraphNode(
        id="page:https://b.ma/1", label="Page", name="b", properties={"url": "https://b.ma/1"}
    )
    graph = GraphSnapshot(
        nodes=[entity, page],
        edges=[GraphEdge(source=page.id, relation="MENTIONS", target=entity.id)],
    )
    service = RagService(
        graph,
        vector_store=_StubStore([(outside, 0.5), (in_graph, 0.5)]),
        client=NvidiaClient(Settings(nvidia_enable_remote_ai=False)),
    )
    answer = service.answer("tourism sector")
    assert answer.evidence[0].chunk_id == "in_graph"
