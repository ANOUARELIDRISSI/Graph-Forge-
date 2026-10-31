from moroccan_crawler.domain.models import (
    ExtractedEntity,
    ExtractedRelation,
    ExtractionResult,
    PageRecord,
)
from moroccan_crawler.graph.store import GraphStore, canonical_relation


def test_relation_uses_typed_entities_and_records_evidence():
    result = ExtractionResult(
        source_chunk_id="chunk-1",
        method="nvidia-llm",
        entities=[
            ExtractedEntity(name="Bank Al-Maghrib", entity_type="Organization", confidence=0.9),
            ExtractedEntity(name="Morocco", entity_type="Country", confidence=0.9),
        ],
        relations=[
            ExtractedRelation(
                subject="Bank Al-Maghrib", predicate="OPERATES_IN", object="Morocco", confidence=0.9
            )
        ],
    )
    store = GraphStore(extractor=lambda chunk: result)
    store.ingest_pages(
        [PageRecord(url="https://www.bkam.ma/", source_domain="bkam.ma", text="Source text")]
    )
    snapshot = store.snapshot()
    relation = next(edge for edge in snapshot.edges if edge.relation == "OPERATES_IN")
    nodes = {node.id: node for node in snapshot.nodes}
    assert nodes[relation.source].label == "Organization"
    assert nodes[relation.target].label == "Country"
    assert relation.properties["chunk"] == "chunk-1"
    assert len([node for node in snapshot.nodes if node.name == "Morocco"]) == 1


def test_free_form_predicates_are_normalized() -> None:
    assert canonical_relation("publie le rapport") == "PUBLISHES"
    assert canonical_relation("is located in") == "OPERATES_IN"
    assert canonical_relation("supervise") == "REGULATES"
    assert canonical_relation("a_un_lien_inconnu") == "RELATED_TO"
