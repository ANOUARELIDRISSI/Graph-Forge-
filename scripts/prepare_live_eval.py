"""Capture actual retrieved contexts and generated answers for a bounded Ragas run."""

import argparse
import json
from pathlib import Path

from moroccan_crawler.ai import NvidiaClient
from moroccan_crawler.chunking import chunk_page
from moroccan_crawler.config import Settings
from moroccan_crawler.domain.models import PageRecord
from moroccan_crawler.vector_store import VectorStore


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--question", default="What types of financial reports are available from AMMC?"
    )
    args = parser.parse_args()
    pages = [
        PageRecord.model_validate_json(line)
        for line in Path("data/pages.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    settings = Settings()
    index = VectorStore(
        NvidiaClient(settings.model_copy(update={"nvidia_enable_remote_ai": False}))
    )
    index.add([chunk for page in pages for chunk in chunk_page(page)])
    contexts = index.search(args.question, limit=3)
    client = NvidiaClient(settings)
    answer = client.generate(
        args.question, "\n".join(f"[{c.source_url}] {c.text}" for c in contexts)
    )
    if not answer:
        raise SystemExit("Remote generation unavailable; refusing to evaluate a fabricated answer")
    row = {
        "user_input": args.question,
        "response": answer,
        "retrieved_contexts": [c.text for c in contexts],
    }
    Path("data/eval_dataset.jsonl").write_text(
        json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "samples": 1,
                "retriever": "offline-hybrid",
                "generator": settings.nvidia_model,
                "review_status": "agent-authored diagnostic; not an independent reviewed benchmark",
            }
        )
    )


if __name__ == "__main__":
    main()
