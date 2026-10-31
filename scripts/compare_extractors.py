"""Compare configured extraction providers on one bounded, non-sensitive sample."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import httpx


def load_env(path: Path = Path(".env")) -> None:
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip() or raw.lstrip().startswith("#") or "=" not in raw:
            continue
        name, value = raw.split("=", 1)
        os.environ.setdefault(name.strip(), value.strip())


def call(name: str, base_url: str, key: str, model: str, extra: dict | None = None) -> dict:
    payload = {
        "model": model,
        "temperature": 0,
        "max_tokens": 1024,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "Extract only grounded entities and relations as JSON with entities "
                    "[{name, entity_type, confidence}] and relations "
                    "[{subject, predicate, object, confidence}]."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Bank Al-Maghrib publie son rapport annuel 2024 au Maroc. "
                    "Le secteur automobile à Tanger a progressé. "
                    "بنك المغرب ينشر بيانات الاقتصاد المغربي."
                ),
            },
        ],
        **(extra or {}),
    }
    started = time.perf_counter()
    try:
        response = httpx.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json=payload,
            timeout=90,
        )
        latency = round(time.perf_counter() - started, 3)
        response.raise_for_status()
        content = response.json()["choices"][0]["message"].get("content")
        parsed = json.loads(content) if content else None
        return {
            "provider": name,
            "ok": isinstance(parsed, dict),
            "model": model,
            "latency_seconds": latency,
            "entities": len((parsed or {}).get("entities", [])),
            "relations": len((parsed or {}).get("relations", [])),
            "error": None,
        }
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
        status = error.response.status_code if isinstance(error, httpx.HTTPStatusError) else None
        return {
            "provider": name,
            "ok": False,
            "model": model,
            "latency_seconds": round(time.perf_counter() - started, 3),
            "entities": 0,
            "relations": 0,
            "error": f"{type(error).__name__}" + (f" ({status})" if status else ""),
        }


def main() -> None:
    load_env()
    results = [
        call(
            "nvidia",
            os.environ.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"),
            os.environ.get("NVIDIA_API_KEY", ""),
            os.environ.get("NVIDIA_EXTRACTION_MODEL", "nvidia/nemotron-3.5-lightning-30b-a3b"),
            {"chat_template_kwargs": {"enable_thinking": False}},
        ),
        call(
            "mistral-small-no-thinking",
            os.environ.get("MISTRAL_API_URL", "https://api.mistral.ai/v1"),
            os.environ.get("MISTRAL_API_KEY", ""),
            "mistral-small-latest",
            {"reasoning_effort": "none"},
        ),
    ]
    Path("data/provider_comparison.json").write_text(
        json.dumps({"sample": "bounded multilingual extraction", "results": results}, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
