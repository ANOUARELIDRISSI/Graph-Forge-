from __future__ import annotations

import json
import threading
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from moroccan_crawler.ai import (
    MistralClient,
    NvidiaClient,
    build_extractor,
    extractor_label,
)
from moroccan_crawler.chunking import chunk_page
from moroccan_crawler.config import Settings
from moroccan_crawler.domain.models import (
    AnswerResponse,
    GraphSnapshot,
    PageRecord,
    QuestionRequest,
)
from moroccan_crawler.graph.analytics import (
    analytics_report,
    find_node,
    neighborhood,
    shortest_path,
)
from moroccan_crawler.graph.neo4j_store import Neo4jGraphStore
from moroccan_crawler.graph.store import GraphStore
from moroccan_crawler.ingestion import load_local_documents
from moroccan_crawler.rag.service import RagService
from moroccan_crawler.vector_qdrant import QdrantVectorStore
from moroccan_crawler.vector_store import VectorStore

app = FastAPI(title="Moroccan Business Intelligence Graph", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_methods=["*"],
    allow_headers=["*"],
)
settings = Settings()
nvidia_client = NvidiaClient(settings)
extraction_client: NvidiaClient | MistralClient = (
    MistralClient(settings) if settings.extraction_provider == "mistral" else nvidia_client
)
extractor = build_extractor(settings, extraction_client)
store = GraphStore(extractor=extractor)
vector_store = (
    QdrantVectorStore(settings, nvidia_client)
    if settings.qdrant_enabled
    else VectorStore(nvidia_client)
)
neo4j_store: Neo4jGraphStore | None = None
active_generation: str | None = None
state_lock = threading.RLock()
rebuild_lock = threading.Lock()
rebuild_status: dict[str, object] = {"state": "idle", "error": None}
app.mount("/app", StaticFiles(directory="frontend", html=True), name="frontend")


def load_pages() -> list[PageRecord]:
    path = Path("data/pages.jsonl")
    cleaned = Path("data/cleaned_pages.jsonl")
    if cleaned.exists() and (not path.exists() or cleaned.stat().st_mtime >= path.stat().st_mtime):
        return [
            PageRecord.model_validate_json(line)
            for line in cleaned.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    if not path.exists():
        return []
    pages = [
        PageRecord.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]
    pdf_path = Path("data/pdf_check.jsonl")
    if pdf_path.exists():
        known_urls = {page.url for page in pages}
        pages.extend(
            page
            for line in pdf_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
            for page in [PageRecord.model_validate_json(line)]
            if page.url not in known_urls
        )
    if settings.include_local_fixtures:
        pages.extend(load_local_documents(Path("data/sources")))
    return pages


def build_graph() -> GraphSnapshot:
    """Build isolated stores, verify counts, then publish one generation atomically."""
    global active_generation, neo4j_store, rebuild_status, store, vector_store
    with rebuild_lock:
        generation = uuid.uuid4().hex
        rebuild_status = {
            "state": "building",
            "generation": generation,
            "started_at": datetime.now(UTC).isoformat(),
            "error": None,
        }
        try:
            pages = load_pages()
            extraction_client.remote_extraction_calls = 0
            candidate_store = GraphStore(extractor=extractor)
            candidate_store.ingest_pages(pages)
            snapshot = candidate_store.snapshot()
            chunks = [chunk for page in pages for chunk in chunk_page(page)]
            candidate_vector = (
                QdrantVectorStore(settings, nvidia_client, generation=generation)
                if settings.qdrant_enabled
                else VectorStore(nvidia_client)
            )
            candidate_vector.add(chunks)
            vector_count = (
                candidate_vector.count()
                if isinstance(candidate_vector, QdrantVectorStore)
                else len(chunks)
            )
            if vector_count != len(chunks):
                raise RuntimeError(f"Qdrant staged {vector_count} points for {len(chunks)} chunks")

            candidate_neo4j: Neo4jGraphStore | None = None
            if settings.neo4j_enabled:
                candidate_neo4j = Neo4jGraphStore(settings)
                candidate_neo4j.stage_snapshot(snapshot, generation)
                neo_nodes, neo_edges = candidate_neo4j.count_generation(generation)
                if (neo_nodes, neo_edges) != (len(snapshot.nodes), len(snapshot.edges)):
                    raise RuntimeError(
                        "Neo4j staged counts do not match the candidate graph: "
                        f"{neo_nodes}/{neo_edges} != {len(snapshot.nodes)}/{len(snapshot.edges)}"
                    )
                candidate_neo4j.activate_generation(generation)

            manifest = {
                "generation": generation,
                "published_at": datetime.now(UTC).isoformat(),
                "documents": len(pages),
                "chunks": len(chunks),
                "nodes": len(snapshot.nodes),
                "edges": len(snapshot.edges),
                "vector_points": vector_count,
                "neo4j": settings.neo4j_enabled,
                "extraction_methods": candidate_store.extraction_methods,
            }
            _atomic_write(Path("data/persistent_graph.json"), snapshot.model_dump_json(indent=2))
            _atomic_write(
                Path("data/persistent_chunks.jsonl"),
                "\n".join(chunk.model_dump_json() for chunk in chunks),
            )
            _atomic_write(Path("data/active_generation.json"), json.dumps(manifest, indent=2))
            with state_lock:
                store = candidate_store
                vector_store = candidate_vector
                neo4j_store = candidate_neo4j
                active_generation = generation
                rebuild_status = {"state": "ready", **manifest, "error": None}
            return snapshot
        except Exception as error:
            rebuild_status = {
                **rebuild_status,
                "state": "failed",
                "error": f"{type(error).__name__}: {error}",
                "finished_at": datetime.now(UTC).isoformat(),
            }
            raise


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(f"{path.suffix}.pending")
    pending.write_text(content, encoding="utf-8")
    pending.replace(path)


def current_graph() -> GraphSnapshot:
    with state_lock:
        snapshot = store.snapshot()
    return snapshot if snapshot.nodes else build_graph()


@app.get("/health")
def health() -> dict[str, object]:
    with state_lock:
        snapshot = store.snapshot()
        generation = active_generation
        neo_connected = (
            neo4j_store is not None
            and generation is not None
            and neo4j_store.active_generation() == generation
        )
    return {
        "status": "ok",
        "version": app.version,
        "components": {
            "graph": {
                "nodes": len(snapshot.nodes),
                "edges": len(snapshot.edges),
                "ready": bool(snapshot.nodes),
            },
            "vector_store": {
                "backend": "qdrant" if settings.qdrant_enabled else "in-memory",
                "ready": True,
            },
            "neo4j": {
                "enabled": settings.neo4j_enabled,
                "connected": neo_connected,
                "generation": generation,
            },
            "remote_ai": {"enabled": settings.nvidia_enable_remote_ai},
            "extraction": {
                "extractor": extractor_label(settings),
                "provider": settings.extraction_provider,
                "model": (
                    settings.mistral_api_model
                    if settings.extraction_provider == "mistral"
                    else settings.nvidia_extraction_model or settings.nvidia_model
                ),
                "thinking_disabled": (
                    settings.mistral_disable_thinking
                    if settings.extraction_provider == "mistral"
                    else settings.nvidia_disable_thinking
                ),
                "methods": store.extraction_methods,
                "llm_failures": extraction_client.failures,
                "last_error": extraction_client.last_error,
                "calls": extraction_client.calls,
                "remote_calls": extraction_client.remote_extraction_calls,
                "cache_hits": extraction_client.cache_hits,
                "cache_entries": (
                    len(extraction_client.cache) if extraction_client.cache is not None else 0
                ),
                "retry_queue": (
                    extraction_client.retry_queue.pending()
                    if extraction_client.retry_queue is not None
                    else 0
                ),
            },
            "rebuild": rebuild_status,
        },
    }


@app.post("/graph/rebuild")
def rebuild_graph() -> dict[str, object]:
    snapshot = build_graph()
    return {
        "status": "published",
        "generation": active_generation,
        "nodes": len(snapshot.nodes),
        "edges": len(snapshot.edges),
    }


@app.get("/graph", response_model=GraphSnapshot)
def graph() -> GraphSnapshot:
    return current_graph()


@app.post("/rag/ask", response_model=AnswerResponse)
def ask(request: QuestionRequest) -> AnswerResponse:
    snapshot = current_graph()
    with state_lock:
        active_vector = vector_store
    return RagService(snapshot, active_vector, extraction_client).answer(request.question)


@app.get("/analytics/sectors")
def sector_analytics() -> dict[str, object]:
    if neo4j_store is not None:
        return {"source": "neo4j", "sectors": neo4j_store.sector_counts()}
    counts: dict[str, int] = {}
    for node in store.snapshot().nodes:
        if node.label == "Sector":
            counts[node.name] = counts.get(node.name, 0) + 1
    return {
        "source": "in-memory",
        "sectors": [
            {"sector": key, "count": value}
            for key, value in sorted(counts.items(), key=lambda item: item[1], reverse=True)
        ],
    }


@app.get("/analytics/graph")
def graph_analytics(limit: int = Query(default=15, ge=1, le=100)) -> dict[str, object]:
    """Graph algorithms: density, connected components, PageRank and communities."""
    return analytics_report(current_graph(), limit=limit)


@app.get("/analytics/paths")
def graph_path(source: str, target: str) -> dict[str, object]:
    """Shortest relationship path between two entities (BFS over the graph)."""
    return shortest_path(current_graph(), source, target)


@app.get("/graph/subgraph")
def graph_subgraph(node: str, hops: int = Query(default=2, ge=1, le=3)) -> GraphSnapshot:
    """Node-centred neighbourhood, used by the explorer's focus mode."""
    snapshot = current_graph()
    seed = find_node(snapshot, node)
    if seed is None:
        return GraphSnapshot()
    return neighborhood(snapshot, {seed.id}, hops=hops)


@app.get("/sources")
def sources(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=50),
    document_type: str | None = Query(default=None, pattern="^(html|pdf|rss)$"),
    domain: str | None = None,
    search: str | None = None,
) -> dict[str, object]:
    pages = load_pages()
    grouped: dict[str, dict[str, object]] = {}
    for record in pages:
        item = grouped.setdefault(
            record.source_domain,
            {"domain": record.source_domain, "documents": 0, "urls": []},
        )
        item["documents"] = int(item["documents"]) + 1
        urls = item["urls"]
        public_url = str(record.canonical_url or record.url)
        if isinstance(urls, list) and public_url not in urls:
            urls.append(public_url)
    filtered = pages
    if document_type:
        filtered = [record for record in filtered if record.document_type == document_type]
    if domain:
        filtered = [record for record in filtered if record.source_domain == domain]
    if search:
        needle = search.casefold().strip()
        filtered = [
            record
            for record in filtered
            if needle
            in " ".join(
                (
                    record.title,
                    record.source_domain,
                    str(record.canonical_url or record.url),
                )
            ).casefold()
        ]
    filtered.sort(key=lambda record: record.published_at or record.crawled_at, reverse=True)
    total_filtered = len(filtered)
    start = (page - 1) * page_size
    selected = filtered[start : start + page_size]
    format_counts = Counter(record.document_type for record in pages)
    return {
        "total_documents": len(pages),
        "filtered_documents": total_filtered,
        "page": page,
        "page_size": page_size,
        "total_pages": (total_filtered + page_size - 1) // page_size,
        "format_counts": {
            kind: format_counts.get(kind, 0) for kind in ("html", "pdf", "rss")
        },
        "sources": sorted(
            grouped.values(), key=lambda item: int(item["documents"]), reverse=True
        ),
        "documents": [
            {
                "id": record.url,
                "url": str(record.canonical_url or record.url),
                "title": record.title or str(record.canonical_url or record.url),
                "domain": record.source_domain,
                "document_type": record.document_type,
                "language": record.language,
                "crawled_at": record.crawled_at.isoformat(),
                "published_at": record.published_at.isoformat()
                if record.published_at
                else None,
                "source_feed_url": record.source_feed_url,
                "text_chars": len(record.text),
                "chunks": len(chunk_page(record)),
            }
            for record in selected
        ],
    }


@app.get("/sources/pdf")
def source_pdf(url: str) -> Response:
    """Proxy only an already indexed PDF so the frontend can display it inline."""
    allowed = {
        str(record.canonical_url or record.url)
        for record in load_pages()
        if record.document_type == "pdf"
    }
    if url not in allowed:
        raise HTTPException(status_code=404, detail="PDF is not present in the active corpus")
    try:
        remote = httpx.get(
            url,
            timeout=45,
            follow_redirects=True,
            headers={"User-Agent": "MoroccanBusinessGraph/1.0 (public research crawler)"},
        )
        remote.raise_for_status()
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail="Unable to retrieve indexed PDF") from error
    if len(remote.content) > 40 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="PDF exceeds the 40 MB viewer limit")
    if not remote.content.startswith(b"%PDF-"):
        raise HTTPException(status_code=502, detail="Indexed URL did not return a PDF")
    return Response(
        content=remote.content,
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="source.pdf"'},
    )


def source_quality(page: PageRecord) -> dict[str, object]:
    domain = page.source_domain.lower()
    official = any(domain.endswith(suffix) for suffix in (".gov.ma", ".ma", ".org.ma"))
    trusted = any(
        token in domain for token in ("hcp", "bankalmaghrib", "oc.gov", "ompic", "maroc.ma")
    )
    provenance = 20 if page.url.startswith(("http://", "https://")) else 4
    authority = 30 if trusted else 22 if official else 8
    completeness = min(30, (8 if page.title else 0) + min(22, len(page.text) // 250))
    freshness = 10 if page.crawled_at else 0
    score = min(100, authority + provenance + completeness + freshness)
    return {
        "url": page.url,
        "domain": domain,
        "score": score,
        "tier": "high" if score >= 75 else "medium" if score >= 50 else "low",
        "reasons": {
            "authority": authority,
            "provenance": provenance,
            "completeness": completeness,
            "freshness": freshness,
        },
    }


@app.get("/data-quality")
def data_quality() -> dict[str, object]:
    ranked = sorted(
        (source_quality(page) for page in load_pages()),
        key=lambda item: int(item["score"]),
        reverse=True,
    )
    return {
        "method": "authority 30 + provenance 20 + completeness 30 + freshness 10",
        "average_score": round(sum(int(item["score"]) for item in ranked) / len(ranked), 1)
        if ranked
        else 0,
        "ranked_documents": ranked,
    }


@app.get("/pipeline/status")
def pipeline_status() -> dict[str, object]:
    pages = load_pages()
    chunks = [chunk for page in pages for chunk in chunk_page(page)]
    snapshot = current_graph()
    return {
        "generation": active_generation,
        "documents": len(pages),
        "chunks": len(chunks),
        "entities": sum(1 for node in snapshot.nodes if node.label not in {"Page", "Source"}),
        "relationships": len(snapshot.edges),
        "document_types": dict(Counter(page.document_type for page in pages)),
        "languages": dict(Counter(page.language for page in pages)),
        "extraction_methods": dict(store.extraction_methods),
        "retry_queue": (
            extraction_client.retry_queue.pending()
            if extraction_client.retry_queue is not None
            else 0
        ),
        "chunking_ready": bool(chunks),
        "entity_extraction_ready": bool(snapshot.nodes),
        "last_ingestion": Path("data/ingestion_checkpoint.json").read_text(encoding="utf-8")
        if Path("data/ingestion_checkpoint.json").exists()
        else None,
        "rebuild": rebuild_status,
    }


@app.get("/evaluation")
def evaluation() -> dict[str, object]:
    """Return retrieval and Ragas metrics for the frontend evaluation view."""
    eval_path = Path("data/eval_results.json")
    ragas_path = Path("data/ragas_results.json")
    retrieval: dict[str, object] = {}
    ragas_rows: list[dict[str, object]] = []
    if eval_path.exists():
        try:
            retrieval = json.loads(eval_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            retrieval = {"error": "Invalid eval_results.json"}
    if ragas_path.exists():
        try:
            ragas_rows = json.loads(ragas_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            ragas_rows = []
    metrics: dict[str, float] = {}
    if ragas_rows:
        names = ("faithfulness", "answer_relevancy", "llm_context_precision_without_reference")
        for name in names:
            values = [float(row[name]) for row in ragas_rows if row.get(name) is not None]
            if values:
                metrics[name] = round(sum(values) / len(values), 4)
    return {
        "retrieval": retrieval,
        "ragas": {"available": bool(ragas_rows), "rows": len(ragas_rows), "metrics": metrics},
        "providers": {
            "extraction": settings.extraction_provider,
            "extraction_model": settings.mistral_api_model,
            "embedding_model": settings.nvidia_embedding_model,
            "hdfs_enabled": settings.hdfs_enabled,
            "spark_enabled": settings.spark_enabled,
        },
    }
