from __future__ import annotations

import csv
import json
from pathlib import Path

from moroccan_crawler.domain.models import PageRecord
from moroccan_crawler.parsing import detect_language, normalize_text


def load_local_documents(directory: Path) -> list[PageRecord]:
    """Load HTML, JSON, CSV, Markdown, and text files with one provenance record each."""
    records: list[PageRecord] = []
    supported = {".html", ".htm", ".json", ".csv", ".md", ".txt"}
    for path in sorted(directory.rglob("*")):
        if path.suffix.lower() not in supported or not path.is_file():
            continue
        raw = path.read_text(encoding="utf-8", errors="replace")
        if path.suffix.lower() == ".json":
            raw = json.dumps(json.loads(raw), ensure_ascii=False)
        elif path.suffix.lower() == ".csv":
            raw = "\n".join(" | ".join(row) for row in csv.reader(raw.splitlines()))
        records.append(
            PageRecord(
                url=f"file://{path.resolve()}",
                title=path.stem,
                text=normalize_text([raw]),
                language=detect_language(raw),
                source_domain="local-file",
            )
        )
    return records
