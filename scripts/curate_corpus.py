"""Promote validated official crawl records, preserving the preceding corpus."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from moroccan_crawler.domain.models import PageRecord
from moroccan_crawler.etl import run_etl


def main() -> None:
    root = Path("data")
    allowed = {"hcp.ma", "bkam.ma", "ammc.ma"}
    records = []
    rejected = 0
    for name in ("pages.jsonl", "crawl_check.jsonl", "pdf_check.jsonl"):
        path = root / name
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            page = PageRecord.model_validate_json(line)
            domain = (urlparse(page.url).hostname or "").removeprefix("www.")
            if domain not in allowed or len(page.text.strip()) < 500 or not page.title:
                rejected += 1
                continue
            records.append(page)
    pages = run_etl(records)
    seen = set()
    unique = []
    for page in pages:
        fingerprint = hashlib.sha256(page.text.encode("utf-8")).hexdigest()
        if fingerprint not in seen:
            unique.append(page)
            seen.add(fingerprint)
    if not unique:
        raise SystemExit("No qualifying records; existing corpus preserved")
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    current = root / "pages.jsonl"
    if current.exists():
        (root / f"pages.before-curation.{stamp}.jsonl").write_bytes(current.read_bytes())
    pending = root / "pages.curated.pending.jsonl"
    pending.write_text("\n".join(page.model_dump_json() for page in unique), encoding="utf-8")
    pending.replace(current)
    report = {
        "documents": len(unique),
        "rejected": rejected,
        "pdfs": sum(page.document_type == "pdf" for page in unique),
        "domains": sorted({page.source_domain for page in unique}),
        "note": "Structural validation and exact deduplication; content accuracy requires review.",
    }
    (root / "corpus_audit.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
