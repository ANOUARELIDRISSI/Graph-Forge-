import os
from pathlib import Path

import httpx
import pytest

from moroccan_crawler.config import Settings
from moroccan_crawler.domain.models import PageRecord
from moroccan_crawler.etl import etl_local, etl_spark, run_etl, spark_available, to_records
from moroccan_crawler.hdfs_store import (
    HdfsDocumentStore,
    RawDocumentStore,
    build_raw_document_store,
)

LONG_TEXT = (
    "Automotive investment in Casablanca and Morocco grows strongly this year "
    "across the tourism and finance sectors."
)


def _pages() -> list[PageRecord]:
    return [
        PageRecord(
            url="https://a.ma/1",
            title="  Automotive   report  ",
            text=f"  {LONG_TEXT}  ",
            source_domain="A.MA",
        ),
        PageRecord(url="https://a.ma/1", title="Duplicate", text=LONG_TEXT, source_domain="a.ma"),
        PageRecord(url="https://c.ma/3", title="Too short", text="tiny", source_domain="c.ma"),
        PageRecord(url="https://b.ma/2", title="Tourism", text=LONG_TEXT, source_domain="B.MA"),
    ]


def test_etl_local_dedupes_filters_and_normalises() -> None:
    cleaned = etl_local(to_records(_pages()))
    urls = [record["url"] for record in cleaned]
    assert urls == ["https://a.ma/1", "https://b.ma/2"]  # duplicate + short document dropped
    assert cleaned[0]["title"] == "Automotive report"  # whitespace collapsed
    assert cleaned[0]["source_domain"] == "a.ma"  # domain lowercased
    assert "text_chars" in cleaned[0]


def test_run_etl_python_path_returns_pages() -> None:
    pages = run_etl(_pages(), use_spark=False)
    assert [str(page.url) for page in pages] == ["https://a.ma/1", "https://b.ma/2"]


def test_etl_preserves_collection_time() -> None:
    original = _pages()
    cleaned = run_etl(original)
    assert cleaned[0].crawled_at == original[0].crawled_at


def test_etl_keeps_valid_duplicate_after_short_record() -> None:
    records = to_records(_pages())
    records.insert(0, {**records[0], "text": "short"})
    assert etl_local(records)[0]["title"] == "Automotive report"


@pytest.mark.skipif(
    os.environ.get("RUN_SPARK_TESTS") != "1",
    reason="set RUN_SPARK_TESTS=1 to run the Spark ETL comparison (needs a working JVM)",
)
def test_spark_etl_matches_python_etl() -> None:
    if not spark_available():
        pytest.skip("pyspark is not installed")
    records = to_records(_pages())
    spark_rows = etl_spark(records)
    assert spark_rows == etl_local(records)


def test_build_raw_store_defaults_to_local(tmp_path: Path) -> None:
    settings = Settings(hdfs_enabled=False, hdfs_fallback_root=str(tmp_path))
    store = build_raw_document_store(settings)
    assert isinstance(store, RawDocumentStore)
    assert Path(store.put("pages.jsonl", "hello")).read_text(encoding="utf-8") == "hello"


def test_hdfs_store_writes_via_webhdfs(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(201, json={"Location": "webhdfs://namenode/file"})

    settings = Settings(
        hdfs_enabled=True, hdfs_url="http://namenode:9870", hdfs_fallback_root=str(tmp_path)
    )
    store = HdfsDocumentStore(settings, transport=httpx.MockTransport(handler))
    result = store.put("pages.jsonl", "hello")
    assert result.startswith("webhdfs://")
    assert store.fell_back is False
    assert seen[0].url.params["op"] == "CREATE"
    assert seen[0].url.params["user.name"] == "hdfs"
    assert seen[0].content == b"hello"
    store.close()


def test_hdfs_store_falls_back_when_namenode_unreachable(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("namenode unreachable", request=request)

    settings = Settings(hdfs_enabled=True, hdfs_fallback_root=str(tmp_path / "raw"))
    store = HdfsDocumentStore(settings, transport=httpx.MockTransport(handler))
    result = store.put("pages.jsonl", "hello")
    assert store.fell_back is True
    assert Path(result).read_text(encoding="utf-8") == "hello"
