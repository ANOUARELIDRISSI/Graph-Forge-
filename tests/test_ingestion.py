from pathlib import Path

from moroccan_crawler.chunking import chunk_page
from moroccan_crawler.domain.models import PageRecord
from moroccan_crawler.ingestion import load_local_documents


def test_chunking_preserves_provenance() -> None:
    page = PageRecord(url="https://example.ma/report", text="x" * 1200, source_domain="example.ma")
    chunks = chunk_page(page, size=500, overlap=50)
    assert len(chunks) >= 2
    assert all(chunk.source_url == page.url for chunk in chunks)


def test_local_heterogeneous_documents_are_loaded() -> None:
    documents = load_local_documents(Path("data/sources"))
    assert len(documents) >= 30
    assert {Path(str(document.url)).suffix for document in documents} >= {
        ".txt",
        ".md",
        ".csv",
        ".json",
    }
