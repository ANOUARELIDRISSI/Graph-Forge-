import json

import httpx

from moroccan_crawler.ai import (
    MistralClient,
    NvidiaClient,
    build_extractor,
    extractor_label,
    heuristic_extract,
)
from moroccan_crawler.config import Settings
from moroccan_crawler.domain.models import PageRecord, TextChunk
from moroccan_crawler.graph.store import GraphStore
from moroccan_crawler.vector_store import VectorStore


def test_offline_entity_extraction() -> None:
    chunk = TextChunk(
        id="c1",
        document_id="d1",
        index=0,
        text="Automotive investment in Casablanca, Maroc",
        source_url="https://example.ma/a",
        language="fr",
    )
    result = heuristic_extract(chunk)
    assert {entity.name for entity in result.entities} >= {"automotive", "Casablanca", "Maroc"}


def test_offline_embedding_and_retrieval() -> None:
    client = NvidiaClient(Settings(nvidia_enable_remote_ai=False))
    store = VectorStore(client)
    chunks = [
        TextChunk(
            id="c1",
            document_id="d1",
            index=0,
            text="automotive investment Casablanca",
            source_url="https://example.ma/a",
            language="fr",
        ),
        TextChunk(
            id="c2",
            document_id="d2",
            index=0,
            text="agriculture water Marrakech",
            source_url="https://example.ma/b",
            language="fr",
        ),
    ]
    store.add(chunks)
    assert store.search("automotive business", limit=1)[0].id == "c1"
    client.close()


def _chunk() -> TextChunk:
    return TextChunk(
        id="c1",
        document_id="d1",
        index=0,
        text="Automotive investment in Casablanca, Maroc",
        source_url="https://example.ma/a",
        language="fr",
    )


def _llm_settings(tmp_path) -> Settings:
    return Settings(
        nvidia_api_key="test-key",
        nvidia_enable_remote_ai=True,
        nvidia_min_request_interval=0,
        nvidia_retry_base_seconds=0,
        extraction_cache_path=str(tmp_path / "cache.jsonl"),
    )


def test_build_extractor_follows_settings(tmp_path) -> None:
    disabled = Settings(nvidia_enable_remote_ai=False)
    assert build_extractor(disabled) is heuristic_extract
    assert extractor_label(disabled) == "heuristic"

    enabled = _llm_settings(tmp_path)
    client = NvidiaClient(enabled)
    assert build_extractor(enabled, client) == client.extract
    assert extractor_label(enabled) == "nvidia-llm"
    client.close()


def test_remote_extractor_parses_llm_json(tmp_path) -> None:
    payload = {
        "entities": [{"name": "OCP", "entity_type": "Organization", "confidence": 0.9}],
        "relations": [{"subject": "OCP", "predicate": "operates_in", "object": "Morocco"}],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"choices": [{"message": {"content": json.dumps(payload)}}]}
        )

    client = NvidiaClient(_llm_settings(tmp_path), transport=httpx.MockTransport(handler))
    result = client.extract(_chunk())
    assert result.method == "nvidia-llm"
    assert result.entities[0].name == "OCP"
    assert result.relations[0].predicate == "operates_in"
    assert client.failures == 0
    client.close()


def test_remote_extractor_failure_degrades_to_heuristic(tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "upstream unavailable"})

    client = NvidiaClient(_llm_settings(tmp_path), transport=httpx.MockTransport(handler))
    result = client.extract(_chunk())
    assert result.method == "heuristic-fallback"
    assert client.failures == 1
    assert client.last_error is not None
    assert {entity.name for entity in result.entities} >= {"automotive", "Maroc"}
    client.close()


def test_graph_store_records_extraction_provenance() -> None:
    page = PageRecord(
        url="https://a.ma/1",
        title="Automotive report",
        text="Automotive investment in Casablanca, Maroc.",
        source_domain="a.ma",
    )
    store = GraphStore()
    store.ingest_pages([page])
    assert set(store.extraction_methods) == {"heuristic"}
    node = next(node for node in store.snapshot().nodes if node.name == "Automotive")
    assert node.properties["extraction"] == "heuristic"


def _cache_settings(tmp_path) -> Settings:
    return Settings(
        nvidia_api_key="test-key",
        nvidia_enable_remote_ai=True,
        nvidia_min_request_interval=0,
        nvidia_retry_base_seconds=0,
        nvidia_max_attempts=1,
        extraction_cache_path=str(tmp_path / "cache.jsonl"),
    )


def test_completed_extraction_is_cached_and_reused(tmp_path) -> None:
    calls = {"n": 0}
    payload = {
        "entities": [{"name": "OCP", "entity_type": "Organization", "confidence": 0.9}],
        "relations": [{"subject": "OCP", "predicate": "operates_in", "object": "Morocco"}],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(
            200, json={"choices": [{"message": {"content": json.dumps(payload)}}]}
        )

    client = NvidiaClient(_cache_settings(tmp_path), transport=httpx.MockTransport(handler))
    first = client.extract(_chunk())
    second = client.extract(_chunk())
    assert first.method == "nvidia-llm"
    assert calls["n"] == 1  # Second lookup is served from disk, not the model.
    assert second.method == "nvidia-llm"
    assert client.cache_hits == 1
    client.close()


def test_failed_extraction_is_not_cached(tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "upstream unavailable"})

    client = NvidiaClient(_cache_settings(tmp_path), transport=httpx.MockTransport(handler))
    client.extract(_chunk())
    client.extract(_chunk())
    assert client.failures == 2  # Failed chunks stay uncached so they are retried.
    assert len(client.cache) == 0
    client.close()


def test_extraction_uses_fast_model_with_thinking_disabled(tmp_path) -> None:
    """The reasoning model burns its budget on hidden tokens and times out."""
    seen: dict[str, object] = {}
    payload = {"entities": [], "relations": []}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(
            200, json={"choices": [{"message": {"content": json.dumps(payload)}}]}
        )

    settings = Settings(
        nvidia_api_key="test-key",
        nvidia_enable_remote_ai=True,
        nvidia_min_request_interval=0,
        nvidia_retry_base_seconds=0,
        nvidia_extraction_model="nvidia/nemotron-3.5-lightning-30b-a3b",
        nvidia_model="mistralai/mistral-large-4-1t-a52b",
        extraction_cache_path=str(tmp_path / "cache.jsonl"),
    )
    client = NvidiaClient(settings, transport=httpx.MockTransport(handler))
    client.extract(_chunk())
    assert seen["model"] == "nvidia/nemotron-3.5-lightning-30b-a3b"
    assert seen["chat_template_kwargs"] == {"enable_thinking": False}
    assert seen["max_tokens"] == 4096
    client.close()


def test_cache_picks_up_another_processes_entries(tmp_path) -> None:
    """The API server and the worker share one cache file on a shared volume."""
    path = str(tmp_path / "cache.jsonl")
    settings = Settings(
        nvidia_api_key="shared-key",
        nvidia_enable_remote_ai=True,
        nvidia_min_request_interval=0,
        extraction_cache_path=path,
    )
    payload = {"entities": [], "relations": []}
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(
            200, json={"choices": [{"message": {"content": json.dumps(payload)}}]}
        )

    reader = NvidiaClient(settings, transport=httpx.MockTransport(handler))
    assert len(reader.cache) == 0  # The shared file does not exist yet.
    writer = NvidiaClient(settings, transport=httpx.MockTransport(handler))
    writer.extract(_chunk())
    assert calls["n"] == 1
    result = reader.extract(_chunk())  # Must observe the writer's entry, no new call.
    assert result.method == "nvidia-llm"
    assert calls["n"] == 1
    assert reader.cache_hits == 1
    reader.close()
    writer.close()


def test_mistral_extraction_disables_reasoning(tmp_path) -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "entities": [
                                        {
                                            "name": "Bank Al-Maghrib",
                                            "entity_type": "Organization",
                                            "confidence": 0.9,
                                        }
                                    ],
                                    "relations": [],
                                }
                            )
                        }
                    }
                ]
            },
        )

    settings = Settings(
        extraction_provider="mistral",
        mistral_api_key="test-key",
        mistral_api_model="mistral-small-latest",
        mistral_min_request_interval=0,
        extraction_cache_path=str(tmp_path / "cache.jsonl"),
    )
    client = MistralClient(settings, transport=httpx.MockTransport(handler))
    result = client.extract(_chunk())
    assert result.method == "mistral-llm"
    assert seen["reasoning_effort"] == "none"
    assert seen["response_format"] == {"type": "json_object"}
    assert extractor_label(settings) == "mistral-llm"
    assert build_extractor(settings, client) == client.extract
    client.close()
