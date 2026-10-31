"""Restart-safe ingestion loop for the local/raw source zone.

Run once with --once for a batch job, or without it as a long-running worker.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

from moroccan_crawler.chunking import chunk_page
from moroccan_crawler.config import Settings
from moroccan_crawler.domain.models import PageRecord
from moroccan_crawler.etl import run_etl, spark_available
from moroccan_crawler.hdfs_store import build_raw_document_store
from moroccan_crawler.ingestion import load_local_documents

DATA = Path("data")
CHECKPOINT = DATA / "ingestion_checkpoint.json"


def load_checkpoint() -> dict[str, str]:
    if not CHECKPOINT.exists():
        return {}
    return json.loads(CHECKPOINT.read_text(encoding="utf-8"))


def ingest_once() -> dict[str, int | str]:
    settings = Settings()
    targets = DATA / "official_targets.txt"
    if targets.exists():
        urls = ",".join(
            line.strip()
            for line in targets.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
        if urls:
            candidate = DATA / "crawl_candidate.jsonl"
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "scrapy",
                    "runspider",
                    "src/moroccan_crawler/spiders/moroccan_pages.py",
                    "-a",
                    f"start_urls_csv={urls}",
                    "-O",
                    str(candidate),
                ],
                check=True,
            )
            records = [
                PageRecord.model_validate_json(line)
                for line in candidate.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            if not records:
                raise RuntimeError("Crawl returned no documents; keeping previous corpus")
            candidate.replace(DATA / "pages.jsonl")
    source_dir = DATA / "sources"
    source_dir.mkdir(parents=True, exist_ok=True)
    documents = load_local_documents(source_dir) if settings.include_local_fixtures else []
    pages_file = DATA / "pages.jsonl"
    if pages_file.exists():
        documents.extend(
            PageRecord.model_validate_json(line)
            for line in pages_file.read_text(encoding="utf-8").splitlines()
            if line
        )
    # Raw zone first: the crawl output is persisted before any transformation.
    raw_store = build_raw_document_store(settings)
    raw_store.put("pages.jsonl", "\n".join(page.model_dump_json() for page in documents))
    # Spark ETL (validation, dedup, normalisation) with a Python fallback.
    documents = run_etl(documents, use_spark=settings.spark_enabled, master=settings.spark_master)
    cleaned_path = DATA / "cleaned_pages.pending.jsonl"
    cleaned_path.write_text(
        "\n".join(page.model_dump_json() for page in documents), encoding="utf-8"
    )
    cleaned_path.replace(DATA / "cleaned_pages.jsonl")
    chunks = [chunk for document in documents for chunk in chunk_page(document)]
    return {
        "documents": len(documents),
        "chunks": len(chunks),
        "raw_zone": "webhdfs" if settings.hdfs_enabled else "local",
        "hdfs_fallback": bool(getattr(raw_store, "fell_back", False)),
        "etl": "spark" if settings.spark_enabled and spark_available() else "python",
        "prepared_at": datetime.now(UTC).isoformat(),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=int, default=300)
    args = parser.parse_args()
    while True:
        try:
            result = ingest_once()
            settings = Settings()
            response = httpx.post(
                f"{settings.ingest_api_url.rstrip('/')}/graph/rebuild", timeout=3600
            )
            response.raise_for_status()
            publication = response.json()
            checkpoint = {
                "last_success": datetime.now(UTC).isoformat(),
                "documents": str(result["documents"]),
                "chunks": str(result["chunks"]),
                "generation": str(publication.get("generation", "")),
            }
            pending = CHECKPOINT.with_suffix(".pending.json")
            pending.write_text(json.dumps(checkpoint, indent=2), encoding="utf-8")
            pending.replace(CHECKPOINT)
            print(json.dumps({**result, **publication}), flush=True)
        except (httpx.HTTPError, OSError, RuntimeError, subprocess.SubprocessError) as error:
            print(f"Ingestion failed: {error}", flush=True)
            if args.once:
                raise
        if args.once:
            return
        time.sleep(max(args.interval, 10))


if __name__ == "__main__":
    main()
