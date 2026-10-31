"""Bounded live NVIDIA diagnostic; never deliberately exhaust provider quotas."""

import json
import time
from pathlib import Path

from moroccan_crawler.ai import NvidiaClient
from moroccan_crawler.chunking import chunk_page
from moroccan_crawler.domain.models import PageRecord


def main():
    client = NvidiaClient()
    if not client.settings.nvidia_enable_remote_ai or not client.settings.nvidia_api_key:
        raise SystemExit("Remote AI must be explicitly enabled and configured")
    checks = {}
    for name, operation in (
        (
            "passage_embeddings",
            lambda: client.embed(["Moroccan business statistics", "Bank Al-Maghrib annual report"]),
        ),
        (
            "query_embedding",
            lambda: client.embed(["Moroccan business statistics"], input_type="query"),
        ),
        (
            "generation",
            lambda: client.generate(
                "Which institution is mentioned?", "This report was published by Bank Al-Maghrib."
            ),
        ),
    ):
        started = time.monotonic()
        try:
            value = operation()
            checks[name] = {"ok": True, "latency_seconds": round(time.monotonic() - started, 2)}
            if name.endswith(("embedding", "embeddings")):
                checks[name].update(count=len(value), dimensions=len(value[0]))
        except Exception as error:  # noqa: BLE001 -- diagnostic records each failure independently
            checks[name] = {"ok": False, "error": type(error).__name__}
    page = PageRecord.model_validate_json(
        Path("data/pages.jsonl").read_text(encoding="utf-8").splitlines()[0]
    )
    result = client.extract(chunk_page(page)[0])
    checks["corpus_extraction"] = {
        "ok": result.method == "nvidia-llm",
        "method": result.method,
        "entities": len(result.entities),
        "relations": len(result.relations),
    }
    report = {
        "chat_model": client.settings.nvidia_model,
        "embedding_model": client.settings.nvidia_embedding_model,
        "min_interval_seconds": client.settings.nvidia_min_request_interval,
        "max_attempts": client.settings.nvidia_max_attempts,
        "rate_limit_scope": "per process; 429 retry tested with mocks, no quota-exhaustion test",
        "checks": checks,
    }
    Path("data/nvidia_live_check.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    client.close()


if __name__ == "__main__":
    main()
