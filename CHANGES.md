# Spec vs. Implementation — Gap Analysis and Enhancements

## Atomic generation publication, synchronized ingestion, and provider decision

- Reworked graph rebuilding as an isolated generation. The API now builds the
  in-memory graph and a generation-filtered Qdrant index, stages generation-keyed
  Neo4j nodes/relationships, verifies exact counts, and only then switches the
  active generation. A failed count check leaves the preceding generation live.
- Added stable evidence-edge keys so Neo4j preserves repeated source/chunk
  provenance instead of collapsing relationships. Free-form multilingual LLM
  predicates are normalized to a controlled graph vocabulary; the active graph
  now uses 13 relationship types instead of hundreds of arbitrary types.
- Removed the duplicate LLM/graph pass from the ingestion worker. The worker now
  performs crawl → raw zone → Spark ETL → atomic cleaned corpus → API publication,
  and advances its checkpoint only after publication succeeds.
- Added a shared file-backed provider request scheduler for API/worker coordination,
  a durable per-chunk retry queue, bounded exponential retry state, and a per-run
  new-call budget. Deferred chunks remain explicitly tagged as heuristic fallbacks
  and are retried by later 30-minute cycles.
- Added an explicit `EXTRACTION_PROVIDER` with Mistral and NVIDIA clients. Mistral
  Small uses `reasoning_effort=none`; NVIDIA Nemotron uses
  `enable_thinking=false`. NVIDIA answer generation also disables thinking.
- Provider comparison on the same bounded multilingual sample: NVIDIA Nemotron
  extraction succeeded in 5.857 s with 7 entities and 3 relations; Mistral's
  models endpoint authenticated but `mistral-small-latest` chat returned HTTP 429.
  NVIDIA therefore remains the configured provider. No credential is logged.
- Increased extraction output capacity to 4,096 tokens and capped output to 25
  entities/relations. The final scheduled cycle used 433 cached/live NVIDIA
  results and 101 provenance-marked fallbacks; 113 durable retry records remain.

### Verified active generation

- Generation: `9d23105e3d9c4038adba43aa6365f32a`
- Corpus: 39 official documents, 534 chunks, Spark ETL.
- In-memory graph: 1,717 nodes and 5,031 edges.
- Neo4j: connected, same generation, 1,717 nodes and 5,031 relationships.
- Qdrant: exactly 534 active-generation vectors.
- Worker checkpoint: same generation, 39 documents and 534 chunks.
- Retrieval diagnostics: vector and GraphRAG both Recall@5 0.75, MRR 0.5833,
  nDCG@5 0.625 on four unreviewed navigation cases.
- Backend: 44 passed, one default Spark skip; opt-in Spark suite 8 passed.
  Ruff lint and full format checks pass. Frontend: 16 tests, TypeScript and
  production build pass (host Node 22.11 remains below Vite's supported 22.12).

### Updated requirement assessment: 70/100

This is an engineering-completion score, not measured answer accuracy. Atomic
cross-store publication and a real successful worker cycle close major reliability
gaps. The score remains limited by 101 fallback chunks, no extraction ground truth,
no reviewed multi-hop benchmark or successful Ragas report, GraphRAG only tying the
vector baseline, no Neo4j GDS comparison, and no deployed HDFS cluster.

## Docker recovery, extraction reliability and retrieval reranking (steps 1–4)

### Step 1 — Docker recovered and the current stack redeployed

- Docker Desktop was restarted and the engine came back (server 29.7.2). All five
  services are up: `api`, `ingest-worker`, `frontend`, `qdrant`, `neo4j`.
- The `api` and `ingest-worker` images were rebuilt from the current source, so the
  running code now matches the repository.
- Verified: `GET /health` returns `status=ok`, `version=0.2.0`, vector backend
  `qdrant`, extractor `nvidia-llm`. The nginx frontend still serves
  `X-Frontend-Release: atlas-modular-v2`.

### Step 3 — LLM extraction made reliable (root cause found and fixed)

- **Root cause of the silent heuristic fallback.** The configured serving model
  `mistralai/mistral-large-4-1t-a52b` is a *reasoning* model. Measured behaviour on a
  single short French chunk:
  - 2 035–4 096 completion tokens of which 1 588–4 095 were hidden
    `reasoning_tokens`; content was empty whenever the budget ran out
    (`finish_reason=length`).
  - ~90–105 seconds per call, which exceeded the 90 s read timeout and produced
    `ReadTimeout` → `heuristic-fallback` for nearly every chunk.
  - When it did answer, its JSON used `{id, type, text}` and sometimes markdown
    fences, which does not match the required `{name, entity_type, confidence}`
    schema and raised a validation error anyway.
- **Fix.** Extraction now runs on a separate, fast instruction model with its
  reasoning pass disabled: `nvidia_extraction_model =
  nvidia/nemotron-3.5-lightning-30b-a3b` plus
  `chat_template_kwargs={"enable_thinking": false}` (`nvidia_disable_thinking=true`).
  `max_tokens` dropped from 8 192 to 2 048. Same prompt and schema; latency fell
  from ~100 s to **0.9–2.9 s per chunk** with no hidden reasoning tokens. The large
  reasoning model is still used for answer generation (`generate`).
- **Verified on the real API.** Six live corpus chunks all returned
  `method=nvidia-llm` (0/6 fallbacks) with real entities and relations, e.g.
  `Tanger-Tetouan -has_sector-> automotive`, and multilingual output including the
  Arabic entity `قطاع الصناعة`.
- **Extraction cache hardened.** The append-only cache keyed by
  `(model, chunk text)` now refreshes itself from disk, so the long-lived API server
  picks up the entries the worker appends instead of re-billing every chunk. Combined
  with the existing "only cache successful extractions" rule, an interrupted job
  resumes and a re-crawl of unchanged pages is free.
- **Rate limiting hardened.** `nvidia_min_request_interval` 2 → 3 s,
  `nvidia_max_attempts` 3 → 4, new `nvidia_retry_base_seconds = 5` with exponential
  backoff and `Retry-After` handling. The attempt count is capped so the worst-case
  cooldown stays under the 60 s guard. A cooldown/exhausted-retry now degrades that
  one chunk to heuristics instead of aborting the ingestion cycle.
- **Diagnosed but not yet closed.** During the worker run the counters showed
  `{"extraction_calls": 75, "cache_hits": 4, "failures": 24}`. A direct reproduction
  (`data/pages.jsonl`, 42 pages → 572 chunks) showed the failures are HTTP
  **429 Too Many Requests**, not schema errors — partly amplified because concurrent
  diagnostic probes shared the same API key. Failed chunks stay uncached, so the next
  cycle retries them; the backoff change above is intended to reduce the count.
- **Observability.** `/health → extraction` now also reports the active
  `model`, `thinking_disabled`, `calls`, `cache_hits` and `cache_entries`.

### Step 4 — GraphRAG reranking (code in place, not yet re-measured)

- `VectorStore`/`QdrantVectorStore` gained `search_scored()`, which returns passages
  with their scores. Qdrant keeps its native cosine score as the primary signal;
  lexical overlap only adds candidates.
- `rag/service.py` replaced the old ad-hoc scoring with `_rank()`, blending
  `0.5 * semantic + 0.3 * lexical + 0.2 * graph_proximity` on a normalised scale, so a
  weak passage can no longer be promoted just because its page appears in the
  subgraph. Added regression tests for both the "cannot promote" and "breaks a tie"
  cases.
- The four navigation diagnostics have **not** been re-run yet, so no claim is made
  that GraphRAG now beats the vector baseline (previously Recall@5 0.50 vs 0.75).

### Verification

- `pytest`: 40 passed, 1 skipped. `ruff check src tests scripts`: clean.
- New tests: extraction payload uses the fast model with thinking disabled; the cache
  picks up another process's entries without a new model call.
- In progress: one full ingestion cycle (crawl → raw → Spark → extraction →
  Neo4j/Qdrant). The crawl produced 42 items; extraction is the remaining long stage.
- Score remains **63/100**. The extraction fix and reranking are code-complete but the
  full-cycle counts/provenance, the re-measured retrieval comparison, the reviewed
  evaluation set, Ragas and real HDFS/Spark verification are still outstanding.

## Frontend delivery and Docker recovery attempt

- Replaced the frontend development-server image with a multi-stage Node build
  and nginx runtime, SPA deep-link fallback, immutable asset caching, no-cache
  HTML and an `X-Frontend-Release: atlas-modular-v2` verification header.
- Current frontend: 16 component tests passed, TypeScript passed, production build
  passed locally. Host Node 22.11 still triggers the Vite supported-version warning.
- Docker rebuild attempted. Daemon commands hung; normal Desktop restart failed.
  Desktop processes were restarted, but engine logs still showed failed internal
  health pings and Docker version returned HTTP 500. A scoped restart of the
  docker-desktop WSL distribution was attempted; successful recovery is unverified.
- No successful Docker rebuild/redeployment is claimed. Prepared current production
  frontend preview on localhost:5174 so the UI can be inspected while Docker is
  unavailable. API-backed functionality still requires the backend to be available.
- Score stays **63/100** until deployment and quality gaps are verified closed.

## Document-diverse retrieval and external-case diagnostics

- GraphRAG now searches 20 passage candidates and reserves evidence slots for
  distinct source documents, rather than letting neighboring chunks fill all five.
- Document-level evaluation deduplicates URLs before applying top-k metrics;
  vector baseline uses the same 20-candidate pool. Added a regression test.
- Added four English/French source-finding diagnostics with explicit expected URLs
  in `evaluation/navigation_cases.jsonl`. These are agent-authored, unreviewed
  navigation questions; `evaluation/README.md` records their limitations.
- On these four cases, vector Recall@5=0.75, MRR=0.5833, nDCG@5=0.625;
  GraphRAG Recall@5=0.50, MRR=0.3333, nDCG@5=0.375. This exposes a reranking
  weakness; no GraphRAG superiority or independent benchmark accuracy is claimed.
- Ragas runner now uses a serial worker, pacing and longer timeout budgets.
- The rerun did not produce a verified result during the bounded wait and was
  interrupted. Reduced request/job budgets to 90/120 seconds and disabled retry
  multiplication for future diagnostics. No successful Ragas report is claimed.
- Verification: 34 backend tests passed, one Spark test skipped; Ruff passed.
- The score remains **63/100** pending a successful full Ragas diagnostic and
  demonstrable retrieval-quality improvements. Adding diagnostics does not by
  itself justify increasing measured quality.

## Live NVIDIA validation and rate-limit handling

- Added configurable request spacing (default 2 seconds), timeout (90 seconds),
  bounded HTTP retries (3 attempts), exponential backoff and Retry-After handling.
  The limiter coordinates NvidiaClient instances in one process, not across
  containers. Long cooldowns cause a deferred/failing call rather than a quota flood.
- Authentication errors are not retried. Exhausted transient errors remain errors.
- Removed silent remote-embedding 404/410 fallback to hash vectors; validates
  embedding counts, non-empty dimensions and finite values.
- Added `scripts/check_nvidia.py`, a bounded sequential live diagnostic.
- Live results (`data/nvidia_live_check.json`): Nemotron 3 Embed 1B returned two
  passage vectors and one query vector, all 2048-dimensional. Generation succeeded
  with the configured Mistral model. A real corpus chunk produced NVIDIA extraction
  with four entities and three relations. No provider quota-exhaustion test was run.
- Added tests for 429 recovery, retry exhaustion, non-retried authentication errors
  and failure on unavailable remote embedding models.
- Updated completion estimate: **63/100**, up from 61 for verified remote API
  operation and request handling. This does not establish extraction accuracy,
  sustained throughput, independent Ragas quality or distributed deployment.

## NVIDIA and Ragas diagnostic verification

- Replaced process-random Python token hashes with stable BLAKE2 hashes for
  reproducible offline embeddings; offline indexes must be rebuilt after this change.
- NVIDIA chat endpoint returned HTTP 200. An extraction request previously failed
  because content was null. Added bounded extraction/generation output budgets and
  explicit empty-generation errors.
- A small diagnostic extraction succeeded (`nvidia-llm`, one entity, two relations).
  A real HCP corpus chunk timed out and fell back. This establishes connectivity,
  not reliable corpus extraction or measured extraction accuracy.
- Pinned compatible evaluation dependencies and installed them alongside Spark.
- Added `prepare_live_eval.py` to capture an actual generated answer and its real
  retrieved contexts. One diagnostic used offline hybrid retrieval and NVIDIA
  generation; no copied title was used as the answer or fabricated reference.
- Ran Ragas on that diagnostic: context precision 0.50; faithfulness timed out
  and was NaN. Preserved the incomplete attempt as
  `data/ragas_attempt_partial.json`; it is not a successful benchmark report.
- Ragas runner now rejects missing scores and writes strict JSON. Default metrics
  are faithfulness and context precision; `--full` also requests answer relevance.
- Backend: 29 passed, 1 skipped; Ruff passed. Stable-hash smoke evaluation remains
  Recall@5 0.6591 on 44 cases/579 chunks; GraphRAG ties the vector baseline.
- Conservative updated completion estimate: **61/100**. Small credit for confirmed
  remote connectivity, reproducibility and a real partial evaluation attempt;
  no credit for independent quality validation, successful faithfulness, or reliable
  full-corpus extraction. Remaining infrastructure/deployment gaps are unchanged.

## Corpus and graph evidence update

- Added `scripts/curate_corpus.py`: validates official domains, minimum text size,
  title presence, normalizes with ETL, removes exact-content duplicates, backs up
  the previous active corpus, and atomically promotes the result.
- Active corpus now contains 44 official documents (43 HTML + 1 PDF), 579 chunks,
  across HCP, Bank Al-Maghrib and AMMC. This is structural curation, not factual
  review or a claim of 44 substantive reports. Audit: `data/corpus_audit.json`.
- Fixed relation endpoint identity: relation nodes reuse the extracted entity
  types, avoiding parallel generic Entity nodes for an Organization/Country.
- Typed relationships now carry extraction method, confidence, source page and
  source chunk properties. Added a regression test for identity/provenance.
- Backend verification: 29 passed, one Spark test skipped; Ruff passed.
- Expanded real-corpus offline smoke test: 44 cases, Recall@5 0.6591, MRR 0.5356,
  nDCG@5 0.5658 for both strategies. Mean latencies: vector 97.07 ms, GraphRAG
  107.36 ms. The larger corpus exposes retrieval limitations hidden by the earlier
  six-document smoke test. This is still self-derived, not independent evaluation.
- A bounded remote extraction connectivity check had remote AI enabled but
  returned `heuristic-fallback`. No successful NVIDIA extraction or Ragas quality
  result is claimed for this pass. The sample text was a diagnostic, not corpus.
- Updated conservative completion estimate: **59/100** (data 11/15; extraction
  10/20; graph 15/20; GraphRAG 14/20; evaluation 3/15; Spark/HDFS 6/10).
  No authentication or Langfuse deduction. Deployment, independent reviewed
  evaluation, successful remote extraction/Ragas and real HDFS remain open.

## Retrieval and evaluation correction

The earlier 64–65/100 estimates over-credit distributed infrastructure and
unmeasured extraction quality. Do not treat them as validated quality scores.

- Fixed local vector retrieval to compare query embeddings against stored
  document embeddings; previously it compared a hash vector to the query vector.
- Added corpus-IDF BM25 with document-length normalization and bounded embedding
  batches; rebuilding the local index replaces old rows.
- Added a semantic-ranking regression test using controlled embeddings.
- Comparative evaluation excludes synthetic local fixtures by default.
- Evaluation now requires an external cases file or explicit `--smoke` consent;
  reports identify smoke/external cases and remote/offline mode.
- Offline is the default for the evaluation harness. `--remote` explicitly enables
  configured remote generation and embeddings. Independent human-reviewed cases,
  successful Ragas results and live distributed execution remain outstanding.
- Backend checks for this change: 28 tests passed, one Spark test skipped in the
  default run; Ruff passed. These are implementation checks, not extraction or
  answer-quality metrics.

## Verification update — 2026-10-31

This section supersedes older status claims below; historical benchmark numbers
are still smoke-test results, not independent accuracy measurements.

- API graph construction now injects the configured extractor. Backend tests
  verify LLM wiring and fallback accounting; deployment and extraction quality
  on a reviewed corpus remain unverified.
- Raw-zone and ETL wiring exists. Fixed preservation of crawl timestamps,
  deterministic first-valid-record deduplication in Spark, and empty Spark input.
- Fixed Spark's Windows Python worker interpreter to use the active virtualenv.
  The opt-in Spark execution test now ran: **8 ETL/raw-zone tests passed**.
  The strengthened parity assertion compares complete records, not only URLs.
- Worker publishes an atomic cleaned corpus; API prefers that corpus when it is
  at least as recent as raw pages. This closes the previous raw-data bypass.
- Dockerfile now installs Java 17 and the bigdata dependency group; startup uses
  `uv run --no-sync` to retain installed extras. Worker enables Spark explicitly.
  These image changes have not been built successfully yet.
- Backend default suite: **27 passed, 1 skipped**. The skipped Spark check was
  separately enabled and passed. Ruff passed after import ordering correction.
- Frontend: **16 component tests passed**, TypeScript passed, production build
  passed. Entry JS is 92.50 KB gzip plus 16.83 KB shared runtime; graph and
  assistant are separate lazy chunks. Host Node 22.11 triggers a Vite supported
  version warning despite a successful build.
- Deployment blocked: Docker context lookup responds, but daemon requests
  (`docker compose ps`) hang and the prior build log remains unchanged. The live
  API still returns the old minimal health payload. No successful redeployment
  or new live end-to-end result is claimed.

### Updated requirement assessment: 64/100

Engineering completion estimate, not an answer-quality measurement:

| Requirement | Points |
|---|---:|
| Crawling and reviewed heterogeneous data | 10/15 |
| Raw zone / Spark integration and execution | 8/15 |
| Extraction / entity resolution | 11/15 |
| Graph storage and analytics | 12/15 |
| GraphRAG and retrieval | 11/15 |
| Independent comparative evaluation / Ragas | 3/15 |
| API / frontend / delivery | 9/10 |

Remaining: responsive Docker deployment and live worker verification; real HDFS
and distributed execution; reviewed corpus and extraction accuracy; independent
multi-hop/Cypher-versus-GraphRAG benchmark and successful Ragas report; access
control; browser E2E tests; remaining connectors. Langfuse remains excluded from
the requested scope and does not cause a scoring deduction.

This document compares [`knowledge-graph-analytics-platform.md`](./knowledge-graph-analytics-platform.md)
(the architecture spec) against the actual code in this repository, lists the gaps that
were found, and records every change that was made to close them — including the
frontend redesign.

It is organised as:

1. [Spec coverage matrix](#1-spec-coverage-matrix)
2. [Backend changes](#2-backend-changes)
3. [Frontend redesign](#3-frontend-redesign)
4. [Verification](#4-verification)
5. [Honest remaining gaps](#5-honest-remaining-gaps)

---

## 1. Spec coverage matrix

The spec defines a 7-stage pipeline (`Crawler → HDFS → ETL+LLM → Spark → Neo4j →
{Graph Analytics, GraphRAG} → Evaluation`) plus phase 7 of the roadmap
(*API, interface, monitoring, access control*).

| Spec element | Before | After |
|---|---|---|
| 1. Crawler (collection, parsing, metadata) | Implemented (Scrapy spiders + local fixtures) | Unchanged — already aligned |
| HDFS raw document store | Partial — `hdfs_store.py` exists but the pipeline fell back to a local `RawDocumentStore` | Unchanged (still a documented gap) |
| 2. ETL + LLM: text extraction, entity detection, relation extraction | Partial — heuristic extraction existed but was **not wired into the graph** in the API path | **Partial** — extraction is now *pluggable* and drives graph construction, but the API still builds `GraphStore()` with the **heuristic extractor by default**; the NVIDIA/LLM extractor (`NvidiaClient.extract`) exists but is **not wired in** |
| 2. ETL + LLM: **entity resolution** | **Missing** — duplicate nodes (`automobile` vs `automotive`, `Maroc` vs `Morocco`) | **Implemented** — normalisation + alias canonicalisation |
| 3. Spark ETl (validation, dedup, transformation) | Partial — `scripts/spark_ingest.py` exists but is not part of the pipeline | Unchanged (documented gap) |
| 3. Neo4j knowledge graph, **graph indexes** | Graph existed; **no constraints/indexes** | **Implemented** — `ensure_schema()` creates a uniqueness constraint and two indexes |
| 4. Graph Analytics: **graph algorithms** | **Missing** — only `/analytics/sectors` (a label count) | **Implemented** — density, degree centrality, PageRank, connected components, communities, k-hop neighbourhood, shortest path |
| 5. GraphRAG: graph retrieval + LLM, context building | Partial — naive "vector search + dump top-k into prompt" | **Implemented** — graph seeds → k-hop subgraph → hybrid lexical/vector re-rank → grounded context with provenance |
| 6. Evaluation: **accuracy, recall, latency, explainability** | Partial — one ad-hoc recall check | **Implemented** — Recall@k, MRR, nDCG@k, mean latency, comparative `vector` vs `graphrag` |
| 7. API | Partial | Extended with analytics / path / subgraph / rich health endpoints |
| 7. Interface | **Unprofessional** — a single minified ~20-line file | **Redesigned** — token-based design system, app shell, 7 pages |
| 7. Monitoring (Langfuse) | Partial — emitted auth errors on every call | **Fixed** — gated behind `LANGFUSE_ENABLED` |
| 7. Access control | **Missing** | Unchanged (documented gap) |

---

## 2. Backend changes

### 2.1 New: entity resolution — `src/moroccan_crawler/graph/resolution.py`

Closes spec §2 *"entity resolution"*, which was entirely absent. Before this change,
the "sector" value from each page was used directly as a node id, so `automobile` and
`automotive` — or `Maroc` and `Morocco` — became **separate nodes for the same thing**,
silently inflating node counts and splitting degree/PageRank mass.

- `fold(text)` — NFKD Unicode fold (strips accents), casefold, collapse non-word runs.
- `resolve(name, entity_type)` — folds the name, applies an alias map
  (`automobile → automotive`, `tourisme → tourism`, `maroc → morocco`,
  `casablanca settat → casablanca-settat`, …), and returns a stable
  `ResolvedEntity(id, name, entity_type, key)` with a `type:canonical` id.
- Type labels map to Neo4j labels (`sector → Sector`, `country → Country`,
  `region → Region`, `organization → Organization`, default `Entity`).

### 2.2 New: graph analytics — `src/moroccan_crawler/graph/analytics.py`

Closes spec §4 *"Cypher queries, graph algorithms"*, which had no implementation beyond
counting sectors.

| Function | Algorithm |
|---|---|
| `graph_summary` | node/edge counts + density |
| `degree_centrality` | undirected degree |
| `pagerank` | damped power iteration (0.85, 40 iterations) |
| `connected_components` | BFS over the undirected adjacency |
| `detect_communities` | deterministic label propagation |
| `ranked_nodes` | centrality + PageRank ranking |
| `find_node` | resolve a name/id (or substring) to a node |
| `neighborhood` | **induced** k-hop subgraph |
| `shortest_path` | BFS, returns `{found, hops, nodes, edges, message}` |
| `analytics_report` | everything above, shaped for the API |

All functions are pure and operate on a `GraphSnapshot`, so they work identically for
the in-memory store and the Neo4j adapter.

### 2.3 Modified: ingestion into the graph — `src/moroccan_crawler/graph/store.py`

Previously the graph was built from a fixed heuristic and the API never invoked the LLM
extraction path. `GraphStore` now:

- accepts an injectable `extractor` (`GraphStore(extractor=…)`, defaulting to
  `heuristic_extract`) so an LLM extractor satisfies the same contract;
- chunks each page and runs extraction per chunk;
- runs every detected entity through `resolve()` before creating the node;
- accumulates `mentions` / `confidence` on nodes instead of creating duplicates;
- emits `page -[MENTIONS]-> entity`, `source -[COVERS]-> entity` and typed
  `subject -[PREDICATE]-> object` edges.

**Correction (verified):** the API still calls `GraphStore()` with no argument, so it
uses `heuristic_extract` — the LLM path is *available*, not *active*. Wiring
`NvidiaClient(settings).extract` into `build_graph()` is still outstanding (see §5).

### 2.4 Modified: GraphRAG — `src/moroccan_crawler/rag/service.py`

Closes spec §5. The old implementation was a baseline: embed the question, take the top
chunks, stuff them into the prompt. `RagService.answer()` is now graph-aware:

1. **Seed matching** — score graph nodes by term overlap, excluding structural
   `Page`/`Source` labels and stopwords, ranked by degree + mentions; keep the top 5.
2. **Subgraph retrieval** — take the induced 2-hop neighbourhood of the seeds.
3. **Hybrid retrieval** — vector search over chunks, then re-rank by lexical overlap
   plus a proximity bonus when a chunk's URL appears in the subgraph.
4. **Context building** — graph triples *and* passages, so the LLM sees both.
5. **Answer + provenance** — returns `evidence[]` (chunk id, url, snippet, score,
   language), `entities[]`, the `subgraph`, `latency_ms`, `grounded` and the `mode`
   (`nvidia-graphrag` when the remote model is used, otherwise `local-baseline`).

### 2.5 Modified: domain models — `src/moroccan_crawler/domain/models.py`

Added the `Evidence` model and extended `AnswerResponse` with `evidence`, `entities`,
`subgraph`, `latency_ms` and `grounded`, so provenance and latency are first-class API
fields rather than something the caller has to infer.

### 2.6 Modified: API — `src/moroccan_crawler/api/main.py` (v0.2.0)

| Endpoint | Purpose |
|---|---|
| `GET /health` | now reports component readiness (graph, vector store, Neo4j, remote AI) |
| `GET /analytics/graph?limit=` | the analytics report (density, centrality, communities) |
| `GET /analytics/paths?source=&target=` | BFS shortest path between two entities |
| `GET /graph/subgraph?node=&hops=` | node-centred neighbourhood for focus mode |
| `POST /graph/rebuild` | deterministic rebuild of the whole graph |

Existing endpoints (`/graph`, `/rag/ask`, `/analytics/sectors`, `/sources`,
`/data-quality`, `/pipeline/status`) are unchanged and still work.

### 2.7 Modified: Neo4j adapter — `src/moroccan_crawler/graph/neo4j_store.py`

`ensure_schema()` now runs before each snapshot write and creates, all with
`IF NOT EXISTS`:

- `CONSTRAINT entity_id` — uniqueness on `Entity.id`
- `INDEX entity_name`
- `INDEX entity_type`

This closes the spec's *"graph indexes"* requirement and also makes re-ingestion
idempotent.

### 2.8 Modified: observability — `src/moroccan_crawler/observability.py`

`observe_generation` previously logged
`Authentication error: Langfuse client initialized without public_key` on **every**
RAG call when Langfuse was unconfigured. It now short-circuits (yielding `None`) when
`LANGFUSE_ENABLED` is false.

### 2.9 Rewritten: evaluation — `scripts/evaluate_rag.py`

Closes spec §6 (*accuracy, recall, latency, explainability*). The script now runs the
**same corpus through two strategies** and reports:

- `recall@5`, `mrr`, `ndcg@5`, `mean_latency_ms` per strategy;
- `best_recall` and a `leader` field that honestly reports `"tie (…)"` instead of
  arbitrarily picking a winner on equal scores;
- a `note` explaining why GraphRAG and vector search converge on a single-hop corpus;
- per-case results to `data/eval_results.json`.

### 2.10 New: tests — `tests/test_graph_analytics.py`

Six tests covering entity-resolution alias merging, resolved nodes after ingestion, the
analytics report, shortest path, induced-subgraph correctness, and graph-aware RAG
returning both a subgraph and evidence.

---

## 3. Frontend redesign

The previous frontend was a **single minified file** with an inline component tree, an
old blue palette, and no shared styling. It has been rebuilt as a proper application.

### 3.1 Design system — `src/style.css`

Replaced the old ~7-line minified stylesheet with a token-based system:

- **Tokens** for surfaces, borders, text, brand, status colours, radii and shadows.
- **App shell**: fixed dark sidebar (brand mark + nav) + sticky translucent topbar + content.
- **Components**: `.card`, `.stat`, `.badge`, `.meter`, `.table`, `.toolbar`, `.alert`,
  `.empty`, `.spinner`, `.button` / `.ghost-button` / `.icon-button` / `.link`.
- **Pages**: explorer grid, analytics grid, overview grid, assistant layout, path chain,
  label lists, stage meters, checklists, evidence panels.
- **Responsive** breakpoints at 1240 / 1080 / 900 / 620 px; the sidebar collapses to a
  horizontal bar and grids go single-column on small screens.

### 3.2 New components

| File | Contents |
|---|---|
| `src/components/Icon.tsx` | inline SVG icon set (17 icons), typed `IconName` union |
| `src/components/ui.tsx` | `Card`, `StatCard`, `Badge`, `Spinner`, `EmptyState`, `ErrorState`, `Meter` |
| `src/components/Layout.tsx` | app shell, nav, live status badges from `/health`, refresh action, `PageHeader` |
| `src/config/palette.ts` | node colour/size mapping shared by the graph canvas and legends |

### 3.3 Pages

| Route | Page | Highlights |
|---|---|---|
| `/` | `OverviewPage` | KPI grid, ingestion stages with meters, graph composition, source coverage |
| `/graph` | `GraphExplorerPage` | force-directed canvas, URL-state search/limit/node, legend, node inspector |
| `/analytics` | `AnalyticsPage` | influence ranking table, communities, shortest-path form + path chain |
| `/assistant` | `AssistantPage` | conversation list, markdown answers, entity chips, evidence drawer, latency/mode badges |
| `/sources` | `SourcesPage` | per-domain coverage table with expandable URL lists |
| `/quality` | `QualityPage` | average score, trust tiers, per-document score meters and reason breakdown |
| `/pipeline` | `PipelinePage` | stage readiness, graph composition, readiness checklist, rebuild action |

### 3.4 Other frontend changes

- `index.html` — was a malformed fragment (`<div id="root">` only, no doctype/head).
  Replaced with a valid document including viewport, description, theme colour and the
  Inter / JetBrains Mono webfonts.
- `src/api/schemas.ts` — added Zod schemas for edges, evidence, answers, analytics,
  paths, quality, health and the enriched pipeline payload.
- `src/api/endpoints.ts` — added `fetchHealth`, `fetchAnalytics`, `fetchQuality`,
  `fetchPath`, `fetchSubgraph`, `rebuildGraph`.
- `src/main.tsx` — replaced the single-file app with a `BrowserRouter` route table.
- `src/components/NotFound.tsx` — restyled onto the design system.
- `src/features/assistant/AssistantPage.tsx` — rewritten onto the design system, now
  surfacing `evidence`, `entities`, `mode`, `grounded` and `latency_ms`.
- Removed `src/features/assistant/assistant.css` (superseded by `style.css`).
- `package.json` — added `@rolldown/binding-win32-x64-msvc` to `optionalDependencies` so
  the rolldown-based Vite build resolves its native binding on Windows.

---

## 4. Verification

| Check | Command | Result |
|---|---|---|
| Backend tests | `uv run pytest` | **16 passed** |
| Backend lint | `uv run ruff check src tests scripts` | **All checks passed** |
| Evaluation | `uv run python scripts/evaluate_rag.py` | see below |
| Frontend types | `npm run typecheck` (`tsc --noEmit`) | **passes** |
| Frontend build | `npm run build` (`tsc -b && vite build`) | **passes** — `dist/` produced |

Evaluation report (`data/eval_results.json`) — 36 documents, 411 chunks, 36
leave-one-out cases:

```
strategy    recall@5   mrr      ndcg@5   mean_latency_ms
vector      0.8889     0.7056   0.7508    97.03
graphrag    0.8889     0.7056   0.7508   106.01
leader: tie (vector, graphrag)
```

**This is a smoke test, not a generalisation score.** The 36 leave-one-out questions are
auto-derived from the indexed documents themselves, and the run includes local fixtures.
That makes the reported `recall@5` optimistic and self-referential — it verifies the
retrieval wiring works, not that retrieval is good. There is **no independent, reviewed
Moroccan evaluation set**, and Ragas (answer faithfulness/relevance) is **not run**. The
numbers above should be read accordingly.

GraphRAG ties vector search on ranking metrics on this corpus while costing ~9 ms more
per query. That is an honest result, not a disguised win: the corpus is single-hop, so
the graph adds explainability (subgraph + provenance) rather than recall.

---

## 5. Honest remaining gaps

These spec items were **not** implemented in this pass and are recorded so they are not
mistaken for done work:

- **LLM extraction not wired** — `NvidiaClient.extract` exists but the API builds the
  graph with the heuristic extractor; extraction quality is therefore unmeasured.
- **Neo4j GDS not used** — the analytics run over an in-memory `GraphSnapshot`, not the
  proposed Neo4j Graph Data Science comparison.
- **Real HDFS** — the pipeline still uses a local `RawDocumentStore` fallback; the
  HDFS client exists but is not the default path.
- **Spark in the pipeline** — `scripts/spark_ingest.py` exists but is not wired into
  `run_pipeline.py`; deduplication/validation currently happen in Python.
- **Distributed deployment** — `docker-compose.yml` runs the API, ingest worker,
  frontend, Qdrant and Neo4j, but **not** an HDFS namenode or a Spark cluster.
- **Access control** — there is no authentication or authorisation layer; the API is
  open. The spec's ethical note about restricting collection/access is therefore only
  partially honoured.
- **PDF/Word/email/database connectors** — parsing supports HTML/text/PDF; other source
  types from the spec's "heterogeneous sources" box are not implemented.
- **Independent evaluation set** — no reviewed Moroccan question/answer set; the current
  metrics are auto-derived and self-referential, and Ragas is not run.
- **Frontend tests** — there are no component or E2E tests; the frontend is verified only
  by typecheck and build.
- **Deployment not rebuilt** — the running container images predate these source changes,
  so the new endpoints are not present in the deployed stack.
- **Frontend bundle size** — the production JS bundle is ~693 kB (214 kB gzipped,
  above the 200 kB target) because the graph canvas library is eagerly imported;
  code-splitting the explorer route would reduce the initial payload.
