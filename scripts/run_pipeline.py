import json
from pathlib import Path

from moroccan_crawler.ai import build_extractor
from moroccan_crawler.chunking import chunk_page
from moroccan_crawler.config import Settings
from moroccan_crawler.domain.models import PageRecord
from moroccan_crawler.graph.store import GraphStore
from moroccan_crawler.ingestion import load_local_documents


def main() -> None:
    pages_path = Path("data/pages.jsonl")
    pages = [
        PageRecord.model_validate_json(line)
        for line in pages_path.read_text(encoding="utf-8").splitlines()
        if line
    ]
    pages.extend(load_local_documents(Path("data/sources")))
    chunks = [chunk for page in pages for chunk in chunk_page(page)]
    snapshot = GraphStore(extractor=build_extractor(Settings()))
    snapshot.ingest_pages(pages)
    Path("data/graph.json").write_text(
        snapshot.snapshot().model_dump_json(indent=2), encoding="utf-8"
    )
    Path("data/chunks.jsonl").write_text(
        "\n".join(chunk.model_dump_json() for chunk in chunks), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "pages": len(pages),
                "chunks": len(chunks),
                "nodes": len(snapshot.snapshot().nodes),
                "edges": len(snapshot.snapshot().edges),
            }
        )
    )


if __name__ == "__main__":
    main()
