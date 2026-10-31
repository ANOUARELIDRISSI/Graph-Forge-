from __future__ import annotations

import json
from pathlib import Path

from moroccan_crawler.domain.models import PageRecord


def main() -> None:
    pages = [
        PageRecord.model_validate_json(line)
        for line in Path("data/pages.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]
    # Official crawled pages are the evaluation corpus; local fixtures stay opt-in.
    unique_pages = {str(page.url): page for page in pages}
    output = Path("data/eval_dataset.jsonl")
    rows = []
    for page in unique_pages.values():
        context = page.text[:800]
        rows.append(
            {
                "user_input": f"What information is available from {page.source_domain}?",
                "response": page.title or page.text[:240],
                "retrieved_contexts": [context],
                "reference": page.title or page.text[:240],
                "reference_contexts": [context],
                "source_url": str(page.url),
            }
        )
    output.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows), encoding="utf-8"
    )
    print(json.dumps({"dataset": str(output), "samples": len(rows)}))


if __name__ == "__main__":
    main()
