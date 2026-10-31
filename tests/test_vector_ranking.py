from moroccan_crawler.domain.models import TextChunk
from moroccan_crawler.vector_store import VectorStore


class SemanticClient:
    def embed(self, texts, input_type="passage"):
        return [[1.0, 0.0] if text in {"query", "relevant"} else [0.0, 1.0] for text in texts]


def test_search_uses_stored_document_embedding():
    store = VectorStore(SemanticClient())
    chunks = [
        TextChunk(
            id=text,
            document_id=text,
            index=0,
            text=text,
            source_url=f"https://example.ma/{text}",
            language="fr",
        )
        for text in ("unrelated", "relevant")
    ]
    store.add(chunks)
    assert store.search("query", 1)[0].id == "relevant"
    store.add(chunks[:1])
    assert len(store._rows) == 1
