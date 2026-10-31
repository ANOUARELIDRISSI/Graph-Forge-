from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Self

from moroccan_crawler.domain.models import TextChunk


class AtomicDirectoryLock:
    """Small cross-process lock that works on the shared Docker data volume."""

    def __init__(self, path: str | Path, timeout: float = 30, stale_after: float = 120) -> None:
        self.path = Path(path)
        self.timeout = timeout
        self.stale_after = stale_after

    def __enter__(self) -> Self:
        deadline = time.monotonic() + self.timeout
        self.path.parent.mkdir(parents=True, exist_ok=True)
        while True:
            try:
                self.path.mkdir()
                return self
            except FileExistsError:
                try:
                    age = time.time() - self.path.stat().st_mtime
                    if age > self.stale_after:
                        self.path.rmdir()
                        continue
                except (FileNotFoundError, OSError):
                    pass
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"Timed out acquiring provider lock {self.path}")
                time.sleep(0.05)

    def __exit__(self, *_: object) -> None:
        try:
            self.path.rmdir()
        except FileNotFoundError:
            pass


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_name(f"{path.name}.{os.getpid()}.pending")
    pending.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    pending.replace(path)


class SharedRateLimiter:
    """Reserve provider request slots across the API and worker processes."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.lock = AtomicDirectoryLock(f"{self.path}.lock")

    def _read(self) -> dict[str, float]:
        try:
            return {key: float(value) for key, value in json.loads(self.path.read_text()).items()}
        except (FileNotFoundError, json.JSONDecodeError, TypeError, ValueError):
            return {}

    def reserve(self, bucket: str, interval: float) -> float:
        if interval <= 0:
            return 0
        with self.lock:
            state = self._read()
            now = time.time()
            slot = max(now, state.get(bucket, 0))
            state[bucket] = slot + interval
            _atomic_json(self.path, state)
        wait = max(0.0, slot - time.time())
        if wait > 60:
            raise RuntimeError("Provider cooldown exceeds 60s; retry this job later")
        time.sleep(wait)
        return wait

    def cooldown(self, bucket: str, delay: float) -> None:
        if delay <= 0:
            return
        with self.lock:
            state = self._read()
            state[bucket] = max(state.get(bucket, 0), time.time() + delay)
            _atomic_json(self.path, state)


class ExtractionRetryQueue:
    """Durable per-chunk retry state; successful extraction removes its entry."""

    def __init__(self, path: str | Path, base_seconds: float, max_seconds: float) -> None:
        self.path = Path(path)
        self.base_seconds = base_seconds
        self.max_seconds = max_seconds
        self.lock = AtomicDirectoryLock(f"{self.path}.lock")

    @staticmethod
    def key(provider: str, model: str, chunk: TextChunk) -> str:
        return hashlib.sha256(f"{provider}\x00{model}\x00{chunk.text}".encode()).hexdigest()

    def _read(self) -> dict[str, dict[str, Any]]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def seconds_until_due(self, provider: str, model: str, chunk: TextChunk) -> float:
        with self.lock:
            record = self._read().get(self.key(provider, model, chunk), {})
        return max(0.0, float(record.get("next_retry_at", 0)) - time.time())

    def fail(self, provider: str, model: str, chunk: TextChunk, error: str) -> dict[str, Any]:
        with self.lock:
            entries = self._read()
            key = self.key(provider, model, chunk)
            attempts = int(entries.get(key, {}).get("attempts", 0)) + 1
            delay = min(self.max_seconds, self.base_seconds * (2 ** (attempts - 1)))
            record = {
                "provider": provider,
                "model": model,
                "chunk": chunk.model_dump(mode="json"),
                "attempts": attempts,
                "next_retry_at": time.time() + delay,
                "last_error": error[:500],
            }
            entries[key] = record
            _atomic_json(self.path, entries)
            return record

    def defer(self, provider: str, model: str, chunk: TextChunk, reason: str) -> None:
        """Schedule untouched work without pretending a provider call failed."""
        with self.lock:
            entries = self._read()
            key = self.key(provider, model, chunk)
            previous = entries.get(key, {})
            entries[key] = {
                "provider": provider,
                "model": model,
                "chunk": chunk.model_dump(mode="json"),
                "attempts": int(previous.get("attempts", 0)),
                "next_retry_at": time.time() + self.base_seconds,
                "last_error": reason[:500],
            }
            _atomic_json(self.path, entries)

    def success(self, provider: str, model: str, chunk: TextChunk) -> None:
        with self.lock:
            entries = self._read()
            if entries.pop(self.key(provider, model, chunk), None) is not None:
                _atomic_json(self.path, entries)

    def pending(self) -> int:
        with self.lock:
            return len(self._read())
