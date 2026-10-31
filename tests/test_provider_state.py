import time

from moroccan_crawler.domain.models import TextChunk
from moroccan_crawler.provider_state import ExtractionRetryQueue, SharedRateLimiter


def chunk() -> TextChunk:
    return TextChunk(
        id="chunk-1",
        document_id="document-1",
        index=0,
        text="Bank Al-Maghrib publie un rapport.",
        source_url="https://www.bkam.ma/report",
        language="fr",
    )


def test_shared_rate_limiter_persists_reserved_slot(tmp_path) -> None:
    path = tmp_path / "limits.json"
    first = SharedRateLimiter(path)
    second = SharedRateLimiter(path)
    first.reserve("provider", 0.01)
    started = time.perf_counter()
    second.reserve("provider", 0.01)
    assert time.perf_counter() - started >= 0.005


def test_retry_queue_is_durable_and_cleared_on_success(tmp_path) -> None:
    path = tmp_path / "retries.json"
    writer = ExtractionRetryQueue(path, base_seconds=30, max_seconds=60)
    record = writer.fail("nvidia", "model", chunk(), "429")
    assert record["attempts"] == 1
    reader = ExtractionRetryQueue(path, base_seconds=30, max_seconds=60)
    assert reader.pending() == 1
    assert reader.seconds_until_due("nvidia", "model", chunk()) > 0
    reader.success("nvidia", "model", chunk())
    assert writer.pending() == 0
