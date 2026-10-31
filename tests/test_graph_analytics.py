from moroccan_crawler.ai import NvidiaClient
from moroccan_crawler.chunking import chunk_page
from moroccan_crawler.config import Settings
from moroccan_crawler.domain.models import PageRecord
from moroccan_crawler.graph.analytics import (
    analytics_report,
    find_node,
    neighborhood,
    shortest_path,
)
from moroccan_crawler.graph.resolution import resolve
from moroccan_crawler.graph.store import GraphStore
from moroccan_crawler.rag.service import RagService
from moroccan_crawler.vector_store import VectorStore


def _corpus() -> list[PageRecord]:
    return [
        PageRecord(
            url="https://a.ma/1",
            title="Automotive report",
            text="Automotive investment in Casablanca, Maroc. Finance supports the sector.",
            source_domain="a.ma",
        ),
        PageRecord(
            url="https://b.ma/2",
            title="Tourism report",
            text="Tourism growth in Marrakech, Maroc.",
            source_domain="b.ma",
        ),
    ]


def _store() -> GraphStore:
    store = GraphStore()
    store.ingest_pages(_corpus())
    return store


def test_entity_resolution_merges_aliases() -> None:
    assert resolve("automobile", "Sector").id == resolve("Automotive", "Sector").id
    assert resolve("Maroc", "Country").name == "Morocco"
    assert resolve("Tourisme", "Sector").name == "Tourism"


def test_ingestion_creates_resolved_entity_nodes() -> None:
    names = {node.name for node in _store().snapshot().nodes}
    assert {"Automotive", "Tourism", "Morocco", "Casablanca"} <= names
    # "automobile"/"tourisme" aliases must not create duplicate nodes.
    assert "Automobile" not in names


def test_graph_analytics_report() -> None:
    report = analytics_report(_store().snapshot())
    assert report["nodes"] > 0
    assert report["centrality"]
    assert report["communities"]
    assert 0.0 <= float(report["density"]) <= 1.0


def test_shortest_path_links_two_entities() -> None:
    result = shortest_path(_store().snapshot(), "sector:automotive", "country:morocco")
    assert result["found"] is True
    assert result["hops"] >= 1
    assert result["nodes"]


def test_neighborhood_is_induced_subgraph() -> None:
    snapshot = _store().snapshot()
    seed = find_node(snapshot, "automotive")
    assert seed is not None
    subgraph = neighborhood(snapshot, {seed.id}, hops=2)
    ids = {node.id for node in subgraph.nodes}
    assert seed.id in ids
    assert all(edge.source in ids and edge.target in ids for edge in subgraph.edges)


def test_graph_aware_rag_returns_subgraph_and_evidence() -> None:
    api_pages = _corpus()
    store = GraphStore()
    store.ingest_pages(api_pages)
    client = NvidiaClient(Settings(nvidia_enable_remote_ai=False))
    vector = VectorStore(client)
    vector.add([chunk for page in api_pages for chunk in chunk_page(page)])
    answer = RagService(store.snapshot(), vector, client=client).answer(
        "Which sectors operate in Morocco?"
    )
    assert answer.mode == "local-baseline"
    assert answer.subgraph is not None
    assert answer.evidence
    assert answer.sources
    assert answer.grounded is True
    assert answer.latency_ms >= 0
    assert "Morocco" in answer.entities
