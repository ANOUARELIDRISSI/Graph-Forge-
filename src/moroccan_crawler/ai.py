from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Callable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import httpx
from pydantic import ValidationError

from moroccan_crawler.config import Settings
from moroccan_crawler.domain.models import (
    ExtractedEntity,
    ExtractedRelation,
    ExtractionResult,
    TextChunk,
)
from moroccan_crawler.provider_state import ExtractionRetryQueue, SharedRateLimiter

Extractor = Callable[[TextChunk], ExtractionResult]


class ExtractionCache:
    """Append-only on-disk cache of completed LLM extractions.

    Keyed by ``(model, chunk text)`` so an interrupted job resumes, a re-crawl
    of unchanged pages is free, and the long-lived worker does not re-call the
    model on every interval. Only *successful* remote extractions are recorded;
    heuristic fallbacks are deliberately left out so the next cycle retries the
    chunks that failed.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._entries: dict[str, dict[str, Any]] = {}
        self._size = -1
        self._load()

    def _load(self) -> None:
        try:
            self._size = self.path.stat().st_size
        except FileNotFoundError:
            self._size = 0
            return
        self._entries = {}
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            key = record.get("key")
            if key:
                self._entries[key] = record.get("result", {})

    def _refresh(self) -> None:
        """Pick up entries another process (e.g. the ingest worker) appended.

        The API and the worker share one cache file, so a long-running server
        would otherwise re-call the model for chunks the worker already paid for.
        """
        try:
            size = self.path.stat().st_size
        except FileNotFoundError:
            return
        if size != self._size:
            self._load()

    @staticmethod
    def key(model: str, chunk: TextChunk) -> str:
        return hashlib.sha256(f"{model}\x00{chunk.text}".encode()).hexdigest()

    def get(self, model: str, chunk: TextChunk) -> ExtractionResult | None:
        self._refresh()
        stored = self._entries.get(self.key(model, chunk))
        if stored is None:
            return None
        try:
            return ExtractionResult.model_validate(stored)
        except ValidationError:
            return None

    def put(self, model: str, chunk: TextChunk, result: ExtractionResult) -> None:
        key = self.key(model, chunk)
        payload = result.model_dump()
        self._entries[key] = payload
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"key": key, "result": payload}, ensure_ascii=False) + "\n")
            handle.flush()
        self._size = self.path.stat().st_size

    def __len__(self) -> int:
        return len(self._entries)


class NvidiaClient:
    """Small OpenAI-compatible NVIDIA client with strict JSON validation."""

    def __init__(
        self, settings: Settings | None = None, transport: httpx.BaseTransport | None = None
    ) -> None:
        self.settings = settings or Settings()
        self.failures = 0
        self.last_error: str | None = None
        self.calls = 0
        self.remote_extraction_calls = 0
        self.cache_hits = 0
        self.cache = (
            ExtractionCache(self.settings.extraction_cache_path)
            if self.settings.extraction_cache_enabled
            else None
        )
        self.rate_limiter = SharedRateLimiter(self.settings.shared_rate_limit_path)
        self.retry_queue = (
            ExtractionRetryQueue(
                self.settings.extraction_retry_queue_path,
                self.settings.extraction_retry_base_seconds,
                self.settings.extraction_retry_max_seconds,
            )
            if self.settings.nvidia_min_request_interval > 0
            else None
        )
        self.client = httpx.Client(
            base_url=self.settings.nvidia_base_url,
            timeout=self.settings.nvidia_timeout_seconds,
            transport=transport,
        )

    def close(self) -> None:
        self.client.close()

    def _post(self, path: str, **kwargs: Any) -> httpx.Response:
        return self._provider_post(
            path,
            base_url=self.settings.nvidia_base_url,
            api_key=self.settings.nvidia_api_key or "",
            interval=self.settings.nvidia_min_request_interval,
            attempts=self.settings.nvidia_max_attempts,
            retry_base=self.settings.nvidia_retry_base_seconds,
            **kwargs,
        )

    def _provider_post(
        self,
        path: str,
        *,
        base_url: str,
        api_key: str,
        interval: float,
        attempts: int,
        retry_base: float,
        **kwargs: Any,
    ) -> httpx.Response:
        """Pace provider traffic across containers and retry transient failures."""
        bucket = hashlib.sha256((base_url + api_key).encode()).hexdigest()
        attempts = max(1, attempts)
        for attempt in range(attempts):
            self.rate_limiter.reserve(bucket, interval)
            response = self.client.post(path, **kwargs)
            if response.status_code not in {429, 500, 502, 503, 504}:
                return response
            delay = float(retry_base * (2**attempt))
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    delay = max(delay, float(retry_after))
                except ValueError:
                    try:
                        delay = max(
                            delay,
                            (
                                parsedate_to_datetime(retry_after) - datetime.now(UTC)
                            ).total_seconds(),
                        )
                    except (ValueError, TypeError, OverflowError):
                        pass
            self.rate_limiter.cooldown(bucket, delay)
            if delay > 60:
                response.raise_for_status()
            if attempt + 1 >= attempts:
                return response
        raise RuntimeError("NVIDIA retry budget exhausted")

    def extract(self, chunk: TextChunk) -> ExtractionResult:
        if not self.settings.nvidia_api_key or not self.settings.nvidia_enable_remote_ai:
            return heuristic_extract(chunk)
        model = self.settings.nvidia_extraction_model or self.settings.nvidia_model
        cached = self.cache.get(model, chunk) if self.cache is not None else None
        if cached is not None:
            self.cache_hits += 1
            self._progress()
            return cached
        if self.retry_queue is not None:
            deferred = self.retry_queue.seconds_until_due("nvidia", model, chunk)
            if deferred > 0:
                self.last_error = f"Deferred durable retry for {round(deferred, 1)} seconds"
                self._progress()
                return heuristic_extract(chunk).model_copy(update={"method": "heuristic-fallback"})
            if self.remote_extraction_calls >= self.settings.extraction_max_new_calls_per_run:
                self.retry_queue.defer("nvidia", model, chunk, "Per-run remote call budget reached")
                self._progress()
                return heuristic_extract(chunk).model_copy(update={"method": "heuristic-fallback"})
        payload: dict[str, Any] = {
            "model": model,
            "temperature": 0,
            "max_tokens": 4096,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Extract Moroccan business entities and relations. Return JSON with "
                        "entities [{name, entity_type, confidence}] and relations "
                        "[{subject, predicate, object, confidence}]. Keep at most 25 distinct "
                        "entities and 25 source-grounded relations. Do not invent facts."
                    ),
                },
                {"role": "user", "content": f"Source chunk {chunk.id}:\n{chunk.text}"},
            ],
        }
        if self.settings.nvidia_disable_thinking:
            # Skip the model's hidden reasoning pass: it dominates latency and,
            # when it exhausts max_tokens, leaves no JSON answer at all.
            payload["chat_template_kwargs"] = {"enable_thinking": False}
        try:
            self.remote_extraction_calls += 1
            response = self._post(
                "/chat/completions",
                headers={"Authorization": f"Bearer {self.settings.nvidia_api_key}"},
                json=payload,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            parsed: dict[str, Any] = json.loads(content)
            result = ExtractionResult(
                source_chunk_id=chunk.id,
                method="nvidia-llm",
                entities=[
                    ExtractedEntity.model_validate(item) for item in parsed.get("entities", [])
                ],
                relations=[
                    ExtractedRelation.model_validate(item) for item in parsed.get("relations", [])
                ],
            )
            if self.cache is not None:
                self.cache.put(model, chunk, result)
            if self.retry_queue is not None:
                self.retry_queue.success("nvidia", model, chunk)
            self._progress()
            return result
        except (httpx.HTTPError, ValueError, TypeError, KeyError, RuntimeError) as error:
            # Never let a remote failure break ingestion: degrade to heuristics and
            # record provenance so the health endpoint can surface the degradation.
            # The result is intentionally not cached, so the next cycle retries it.
            self.failures += 1
            self.last_error = f"{type(error).__name__}: {error}"
            if self.retry_queue is not None:
                self.retry_queue.fail("nvidia", model, chunk, self.last_error)
            self._progress()
            return heuristic_extract(chunk).model_copy(update={"method": "heuristic-fallback"})

    def _progress(self) -> None:
        """Emit a periodic counter so a long extraction job is observable."""
        self.calls += 1
        if self.calls % 25 == 0:
            print(
                json.dumps(
                    {
                        "extraction_calls": self.calls,
                        "cache_hits": self.cache_hits,
                        "failures": self.failures,
                    }
                ),
                flush=True,
            )

    def embed(self, texts: list[str], input_type: str = "passage") -> list[list[float]]:
        if not texts:
            return []
        if not self.settings.nvidia_api_key or not self.settings.nvidia_enable_remote_ai:
            return [deterministic_embedding(text) for text in texts]
        response = self._post(
            "/embeddings",
            headers={"Authorization": f"Bearer {self.settings.nvidia_api_key}"},
            json={
                "model": self.settings.nvidia_embedding_model,
                "input": texts,
                "input_type": input_type,
                "encoding_format": "float",
            },
        )
        response.raise_for_status()
        vectors = [
            item["embedding"]
            for item in sorted(response.json()["data"], key=lambda item: item["index"])
        ]
        if (
            len(vectors) != len(texts)
            or not vectors
            or not vectors[0]
            or any(
                len(vector) != len(vectors[0]) or not all(math.isfinite(value) for value in vector)
                for vector in vectors
            )
        ):
            raise ValueError("NVIDIA returned incomplete or invalid embeddings")
        return vectors

    def generate(self, question: str, context: str) -> str | None:
        if not self.settings.nvidia_api_key or not self.settings.nvidia_enable_remote_ai:
            return None
        response = self._post(
            "/chat/completions",
            headers={"Authorization": f"Bearer {self.settings.nvidia_api_key}"},
            json={
                "model": self.settings.nvidia_model,
                "temperature": 0.1,
                "max_tokens": 4096,
                "messages": [
                    {
                        "role": "system",
                        "content": "Answer Moroccan business questions only from the supplied source context. Be concise and say when evidence is insufficient.",
                    },
                    {
                        "role": "user",
                        "content": f"Question: {question}\n\nSource context:\n{context}",
                    },
                ],
                **(
                    {"chat_template_kwargs": {"enable_thinking": False}}
                    if self.settings.nvidia_disable_thinking
                    else {}
                ),
            },
        )
        response.raise_for_status()
        choice = response.json()["choices"][0]
        content = choice["message"].get("content")
        if not content:
            raise ValueError(
                f"Generation returned no answer (finish_reason={choice.get('finish_reason')})"
            )
        return content.strip()


class MistralClient(NvidiaClient):
    """Mistral chat client for extraction/generation; NVIDIA remains the embedder."""

    def __init__(
        self, settings: Settings | None = None, transport: httpx.BaseTransport | None = None
    ) -> None:
        super().__init__(settings, transport)
        self.client.close()
        self.client = httpx.Client(
            base_url=self.settings.mistral_api_url,
            timeout=self.settings.mistral_timeout_seconds,
            transport=transport,
        )
        self.retry_queue = (
            ExtractionRetryQueue(
                self.settings.extraction_retry_queue_path,
                self.settings.extraction_retry_base_seconds,
                self.settings.extraction_retry_max_seconds,
            )
            if self.settings.mistral_min_request_interval > 0
            else None
        )

    def _post(self, path: str, **kwargs: Any) -> httpx.Response:
        return self._provider_post(
            path,
            base_url=self.settings.mistral_api_url,
            api_key=self.settings.mistral_api_key or "",
            interval=self.settings.mistral_min_request_interval,
            attempts=self.settings.mistral_max_attempts,
            retry_base=self.settings.nvidia_retry_base_seconds,
            **kwargs,
        )

    def extract(self, chunk: TextChunk) -> ExtractionResult:
        if not self.settings.mistral_api_key:
            return heuristic_extract(chunk)
        model = self.settings.mistral_api_model
        cached = self.cache.get(model, chunk) if self.cache is not None else None
        if cached is not None:
            self.cache_hits += 1
            self._progress()
            return cached
        if self.retry_queue is not None:
            deferred = self.retry_queue.seconds_until_due("mistral", model, chunk)
            if deferred > 0:
                self.last_error = f"Deferred durable retry for {round(deferred, 1)} seconds"
                self._progress()
                return heuristic_extract(chunk).model_copy(update={"method": "heuristic-fallback"})
            if self.remote_extraction_calls >= self.settings.extraction_max_new_calls_per_run:
                self.retry_queue.defer(
                    "mistral", model, chunk, "Per-run remote call budget reached"
                )
                self._progress()
                return heuristic_extract(chunk).model_copy(update={"method": "heuristic-fallback"})
        payload: dict[str, Any] = {
            "model": model,
            "temperature": 0,
            "max_tokens": 4096,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Extract Moroccan business entities and relations. Return JSON with "
                        "entities [{name, entity_type, confidence}] and relations "
                        "[{subject, predicate, object, confidence}]. Keep at most 25 distinct "
                        "entities and 25 source-grounded relations. Do not invent facts."
                    ),
                },
                {"role": "user", "content": f"Source chunk {chunk.id}:\n{chunk.text}"},
            ],
        }
        if self.settings.mistral_disable_thinking:
            payload["reasoning_effort"] = "none"
        try:
            self.remote_extraction_calls += 1
            response = self._post(
                "/chat/completions",
                headers={"Authorization": f"Bearer {self.settings.mistral_api_key}"},
                json=payload,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            parsed: dict[str, Any] = json.loads(content)
            result = ExtractionResult(
                source_chunk_id=chunk.id,
                method="mistral-llm",
                entities=[
                    ExtractedEntity.model_validate(item) for item in parsed.get("entities", [])
                ],
                relations=[
                    ExtractedRelation.model_validate(item) for item in parsed.get("relations", [])
                ],
            )
            if self.cache is not None:
                self.cache.put(model, chunk, result)
            if self.retry_queue is not None:
                self.retry_queue.success("mistral", model, chunk)
            self._progress()
            return result
        except (httpx.HTTPError, ValueError, TypeError, KeyError, RuntimeError) as error:
            self.failures += 1
            self.last_error = f"{type(error).__name__}: {error}"
            if self.retry_queue is not None:
                self.retry_queue.fail("mistral", model, chunk, self.last_error)
            self._progress()
            return heuristic_extract(chunk).model_copy(update={"method": "heuristic-fallback"})

    def generate(self, question: str, context: str) -> str | None:
        if not self.settings.mistral_api_key:
            return None
        payload: dict[str, Any] = {
            "model": self.settings.mistral_api_model,
            "temperature": 0.1,
            "max_tokens": 2048,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Answer Moroccan business questions only from supplied context. "
                        "Say when evidence is insufficient."
                    ),
                },
                {"role": "user", "content": f"Question: {question}\n\nSource context:\n{context}"},
            ],
        }
        if self.settings.mistral_disable_thinking:
            payload["reasoning_effort"] = "none"
        response = self._post(
            "/chat/completions",
            headers={"Authorization": f"Bearer {self.settings.mistral_api_key}"},
            json=payload,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"].get("content")
        if not content:
            raise ValueError("Mistral generation returned no answer")
        return content.strip()


def deterministic_embedding(text: str, dimensions: int = 256) -> list[float]:
    """Offline fallback for tests/dev; production uses NVIDIA embeddings."""
    values = [0.0] * dimensions
    for token in re.findall(r"\w+", text.casefold(), re.UNICODE):
        index = int.from_bytes(
            hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest(), "big"
        )
        values[index % dimensions] += 1.0
    norm = math.sqrt(sum(value * value for value in values)) or 1.0
    return [value / norm for value in values]


# Offline gazetteer of Moroccan business entities. Keys are the canonical surface
# forms used as display names; values are the entity types the resolver labels by.
# This keeps the default (no-API-key) extraction path useful instead of returning
# a handful of hardcoded sectors with no relations.
_GAZETTEER: dict[str, str] = {
    # Sectors
    "automotive": "Sector",
    "automobile": "Sector",
    "tourism": "Sector",
    "tourisme": "Sector",
    "agriculture": "Sector",
    "agroalimentaire": "Sector",
    "finance": "Sector",
    "banque": "Sector",
    "banking": "Sector",
    "energy": "Sector",
    "textile": "Sector",
    "aerospace": "Sector",
    "construction": "Sector",
    "mining": "Sector",
    "offshoring": "Sector",
    # Country
    "Morocco": "Country",
    "Maroc": "Country",
    # Regions / cities
    "Casablanca": "Region",
    "Rabat": "Region",
    "Tanger": "Region",
    "Marrakech": "Region",
    "Agadir": "Region",
    "Fes": "Region",
    "Oujda": "Region",
    "Kenitra": "Region",
    "Tanger-Tetouan": "Region",
    "Casablanca-Settat": "Region",
    "Rabat-Sale-Kenitra": "Region",
    # Organizations
    "Bank Al-Maghrib": "Organization",
    "Haut-Commissariat au Plan": "Organization",
    "HCP": "Organization",
    "AMMC": "Organization",
    "OCP": "Organization",
    "ONCF": "Organization",
    "Maroc Telecom": "Organization",
    "Attijariwafa Bank": "Organization",
    "Tanger Med": "Organization",
    "Stellantis": "Organization",
    "Renault": "Organization",
}

# Longest keys first so multi-word names win over their substrings.
_GAZETTEER_ALTERNATION = "|".join(
    re.escape(term) for term in sorted(_GAZETTEER, key=len, reverse=True)
)

# Explicit connectives keep relations text-grounded: a relation is only emitted
# when the source text actually reads "<entity> <connector> <entity>".
_RELATION_PATTERN = re.compile(
    rf"(?P<subject>{_GAZETTEER_ALTERNATION})\s+"
    rf"(?:in|au|en|à|dans|vers|and|et)\s+"
    rf"(?P<object>{_GAZETTEER_ALTERNATION})",
    re.IGNORECASE,
)


def heuristic_extract(chunk: TextChunk) -> ExtractionResult:
    """Deterministic, dependency-free extraction used when the LLM is disabled.

    Entities come from a gazetteer of Moroccan business terms; relations are only
    emitted for explicit ``<subject> <connector> <object>`` phrases so nothing is
    invented. Every result is tagged ``heuristic`` for provenance.
    """
    entities = [
        ExtractedEntity(name=name, entity_type=kind, confidence=0.35)
        for name, kind in _GAZETTEER.items()
        if re.search(rf"\b{re.escape(name)}\b", chunk.text, re.IGNORECASE)
    ]
    entity_types = {entity.name.casefold(): entity.entity_type for entity in entities}
    relations: list[ExtractedRelation] = []
    seen: set[tuple[str, str, str]] = set()
    for match in _RELATION_PATTERN.finditer(chunk.text):
        subject = match.group("subject")
        obj = match.group("object")
        if subject.casefold() == obj.casefold():
            continue
        predicate = (
            "OPERATES_IN" if entity_types[obj.casefold()] in {"Region", "Country"} else "RELATED_TO"
        )
        key = (subject.casefold(), predicate, obj.casefold())
        if key in seen:
            continue
        seen.add(key)
        relations.append(
            ExtractedRelation(subject=subject, predicate=predicate, object=obj, confidence=0.3)
        )
    return ExtractionResult(
        source_chunk_id=chunk.id, entities=entities, relations=relations, method="heuristic"
    )


def extractor_label(settings: Settings) -> str:
    """Human-readable name of the extractor that will actually be used."""
    if settings.extraction_provider == "mistral" and settings.mistral_api_key:
        return "mistral-llm"
    if (
        settings.extraction_provider == "nvidia"
        and settings.nvidia_enable_remote_ai
        and settings.nvidia_api_key
    ):
        return "nvidia-llm"
    return "heuristic"


def build_extractor(
    settings: Settings, client: NvidiaClient | MistralClient | None = None
) -> Extractor:
    """Return the configured extractor, falling back to heuristics when disabled.

    The remote extractor degrades per-chunk inside ``NvidiaClient.extract``, so a
    network or schema failure never aborts graph construction.
    """
    if settings.extraction_provider == "mistral" and settings.mistral_api_key:
        return (client or MistralClient(settings)).extract
    if (
        settings.extraction_provider == "nvidia"
        and settings.nvidia_enable_remote_ai
        and settings.nvidia_api_key
    ):
        return (client or NvidiaClient(settings)).extract
    return heuristic_extract
