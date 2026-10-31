# Moroccan Knowledge Crawler

This is a small, testable Scrapy crawler for the knowledge-graph pipeline. It
adds provenance, lightweight Arabic/French detection, a Morocco context label,
robots compliance, and conservative request pacing.

## Run the safe smoke test

```powershell
uv sync
uv run scrapy runspider src/moroccan_crawler/spiders/moroccan_pages.py
uv run pytest
```

The default target is `quotes.toscrape.com`, a public Scrapy tutorial site.
For an authorized Moroccan source, provide explicit URLs:

```powershell
uv run scrapy runspider src/moroccan_crawler/spiders/moroccan_pages.py `
  -a start_urls_csv="https://example.ma/"
```

Only crawl sources you are authorized to access. Keep `ROBOTSTXT_OBEY` enabled,
respect terms and rate limits, and do not infer that extracted associations
are verified facts. Never place credentials in source code or crawler output.

## Modular application

The React/TypeScript explorer lives in `frontend/` and uses
`react-force-graph-2d` for a zoomable, pannable canvas. It supports 50, 100,
and 200 visible nodes. The API, graph pipeline, crawler, and frontend can be
started with Docker Compose:

```powershell
docker compose up --build
```

The `ingest-worker` service runs the restart-safe persistent ingestion loop.
It writes `data/ingestion_checkpoint.json`, `data/persistent_chunks.jsonl`,
and `data/persistent_graph.json`. Run one batch manually with:

```powershell
$env:PYTHONPATH="src"
uv run python scripts/persistent_ingest.py --once
```

Architecture diagrams for the LaTeX report are in `drawio/`, and the report
skeleton is `report/architecture_report.tex`.

For local document testing, run `uv run python scripts/seed_demo_sources.py`.
It creates 30 heterogeneous `.txt`, `.md`, `.csv`, and `.json` documents;
`scripts/run_pipeline.py` loads and chunks them while preserving provenance.

## AI extraction and retrieval

The AI layer supports `EXTRACTION_PROVIDER=nvidia|mistral|heuristic` for
structured entity/relation extraction. NVIDIA remains the embedding provider,
using `nvidia/nemotron-3-embed-1b`. Both remote extractors disable reasoning;
NVIDIA uses `chat_template_kwargs.enable_thinking=false`, while Mistral Small
uses `reasoning_effort=none`. Remote calls are disabled by default so tests and
local development do not spend quota.

Provider calls are paced across containers through a shared state file. Failed
or deferred chunks enter `data/extraction_retry_queue.json` and later ingestion
cycles retry them. A rebuild stages generation-isolated Qdrant and Neo4j data,
checks their counts, and only then publishes the new active generation. Inspect
`GET /health` and `GET /pipeline/status` for the generation and extraction
provenance counters.

