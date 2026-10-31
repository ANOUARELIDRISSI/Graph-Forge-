"""Compare retrieval strategies with Recall@k, MRR, nDCG@k and latency.

Two strategies run over the same corpus and ground truth:
* ``vector``  - hybrid lexical/embedding passage search only.
* ``graphrag`` - graph seed matching + k-hop subgraph expansion + passages.

Each document contributes one leave-one-out query taken from its own content,
so a hit means the retriever recovered the document the query came from.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import time
from pathlib import Path

from moroccan_crawler.ai import NvidiaClient
from moroccan_crawler.chunking import chunk_page
from moroccan_crawler.config import Settings
from moroccan_crawler.domain.models import PageRecord
from moroccan_crawler.graph.store import GraphStore
from moroccan_crawler.rag.service import RagService
from moroccan_crawler.vector_store import VectorStore

K = 5
DATA = Path("data")


def load_pages() -> list[PageRecord]:
    pages: list[PageRecord] = []
    for name in ("pages.jsonl", "pdf_check.jsonl"):
        path = DATA / name
        if path.exists():
            pages.extend(
                PageRecord.model_validate_json(line)
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            )
    return list({str(page.url): page for page in pages}.values())


def build_cases(pages: list[PageRecord]) -> list[dict[str, str]]:
    cases: list[dict[str, str]] = []
    for page in pages:
        words = re.findall(r"\w+", page.text)
        signature = " ".join(words[:12]) if len(words) >= 4 else page.title
        if len(signature) < 4:
            continue
        cases.append({"question": signature, "expected_url": str(page.url)})
    return cases


def rank_metrics(ranking: list[str], expected: str) -> dict[str, float | int | None]:
    ranking = list(dict.fromkeys(ranking))[:K]
    rank = next((index for index, url in enumerate(ranking) if url == expected), None)
    within_k = rank is not None and rank < K
    return {
        "rank": rank,
        "recall": 1.0 if within_k else 0.0,
        "rr": 1.0 / (rank + 1) if rank is not None else 0.0,
        "ndcg": 1.0 / math.log2(rank + 2) if within_k else 0.0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, help="Reviewed JSONL: question, expected_url")
    parser.add_argument(
        "--smoke", action="store_true", help="Explicitly allow self-derived smoke questions"
    )
    parser.add_argument(
        "--remote", action="store_true", help="Use configured NVIDIA generation/embeddings"
    )
    args = parser.parse_args()
    if not args.cases and not args.smoke:
        parser.error("Supply --cases reviewed.jsonl, or explicitly select --smoke")
    pages = load_pages()
    if not pages:
        raise SystemExit("No corpus found in data/. Run the ingestion pipeline first.")
    chunks = [chunk for page in pages for chunk in chunk_page(page)]
    settings = Settings()
    if not args.remote:
        settings = settings.model_copy(update={"nvidia_enable_remote_ai": False})
    client = NvidiaClient(settings)
    vector = VectorStore(client)
    vector.add(chunks)
    graph = GraphStore()
    graph.ingest_pages(pages)
    rag = RagService(graph.snapshot(), vector, client=client)

    strategies: dict[str, dict[str, float]] = {}
    per_case: list[dict[str, object]] = []
    cases = (
        [
            json.loads(line)
            for line in args.cases.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if args.cases
        else build_cases(pages)
    )
    known_urls = {page.url for page in pages}
    if not cases or any(
        not case.get("question") or case.get("expected_url") not in known_urls for case in cases
    ):
        raise SystemExit("Cases must have questions and expected URLs present in the real corpus")
    for case in cases:
        row: dict[str, object] = {
            "question": case["question"],
            "expected_url": case["expected_url"],
        }
        started = time.perf_counter()
        hits = vector.search(case["question"], limit=20)
        row["vector"] = {
            **rank_metrics([str(hit.source_url) for hit in hits], case["expected_url"]),
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        }
        started = time.perf_counter()
        answer = rag.answer(case["question"])
        row["graphrag"] = {
            **rank_metrics(answer.sources, case["expected_url"]),
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        }
        per_case.append(row)

    for strategy in ("vector", "graphrag"):
        count = len(per_case) or 1
        strategies[strategy] = {
            f"recall@{K}": round(
                sum(float(row[strategy]["recall"]) for row in per_case) / count, 4
            ),
            "mrr": round(sum(float(row[strategy]["rr"]) for row in per_case) / count, 4),
            f"ndcg@{K}": round(sum(float(row[strategy]["ndcg"]) for row in per_case) / count, 4),
            "mean_latency_ms": round(
                sum(float(row[strategy]["latency_ms"]) for row in per_case) / count, 2
            ),
        }

    recall_key = f"recall@{K}"
    best_recall = max(strategies[name][recall_key] for name in strategies)
    leaders = [name for name in strategies if strategies[name][recall_key] == best_recall]
    report = {
        "evaluation_type": "external-cases" if args.cases else "self-derived-smoke",
        "remote_ai": args.remote,
        "corpus": {"documents": len(pages), "chunks": len(chunks), "k": K, "cases": len(per_case)},
        "strategies": strategies,
        "best_recall": best_recall,
        "leader": leaders[0] if len(leaders) == 1 else f"tie ({', '.join(leaders)})",
        "note": (
            "Compare rankings below; externally supplied cases still require human review. "
            "Smoke questions do not measure generalization. Offline runs use hash embeddings."
        ),
        "cases": per_case,
    }
    (DATA / "eval_results.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {k: report[k] for k in ("corpus", "strategies", "best_recall", "leader")}, indent=2
        )
    )


if __name__ == "__main__":
    main()
