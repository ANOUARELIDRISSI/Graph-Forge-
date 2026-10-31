import httpx
import pytest

from moroccan_crawler.ai import NvidiaClient
from moroccan_crawler.config import Settings


def test_429_retries_then_validates_embedding(monkeypatch):
    monkeypatch.setattr("moroccan_crawler.provider_state.time.sleep", lambda delay: None)
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.1, 0.2]}]})

    client = NvidiaClient(
        Settings(
            nvidia_api_key="rate-test", nvidia_enable_remote_ai=True, nvidia_min_request_interval=0
        ),
        httpx.MockTransport(handler),
    )
    assert client.embed(["query"]) == [[0.1, 0.2]]
    assert len(calls) == 2
    client.close()


def test_missing_remote_model_does_not_silently_use_hash_vectors():
    client = NvidiaClient(
        Settings(
            nvidia_api_key="missing-test",
            nvidia_enable_remote_ai=True,
            nvidia_min_request_interval=0,
        ),
        httpx.MockTransport(lambda request: httpx.Response(404)),
    )
    with pytest.raises(httpx.HTTPStatusError):
        client.embed(["query"])
    client.close()


def test_authentication_failure_is_not_retried():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(401)

    client = NvidiaClient(
        Settings(
            nvidia_api_key="auth-failure-test",
            nvidia_enable_remote_ai=True,
            nvidia_min_request_interval=0,
        ),
        httpx.MockTransport(handler),
    )
    with pytest.raises(httpx.HTTPStatusError):
        client.embed(["query"])
    assert len(calls) == 1
    client.close()


def test_retry_budget_is_bounded(monkeypatch):
    monkeypatch.setattr("moroccan_crawler.provider_state.time.sleep", lambda delay: None)
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": "0"})

    client = NvidiaClient(
        Settings(
            nvidia_api_key="bounded-retry-test",
            nvidia_enable_remote_ai=True,
            nvidia_min_request_interval=0,
            nvidia_max_attempts=2,
        ),
        httpx.MockTransport(handler),
    )
    with pytest.raises(httpx.HTTPStatusError):
        client.embed(["query"])
    assert len(calls) == 2
    client.close()
