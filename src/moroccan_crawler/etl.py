"""Validation, deduplication and normalisation stage of the ingestion pipeline.

The spec places Spark between the raw zone and the graph. This module is the
single entry point the ingestion worker calls: :func:`run_etl` uses Spark when
``SPARK_ENABLED`` is set *and* pyspark is installed, and otherwise runs an
equivalent pure-Python implementation so local runs and tests stay
dependency-light. Both paths apply the same rules:

* collapse whitespace in ``title`` and ``text``;
* lowercase ``source_domain``;
* drop documents whose normalised text is shorter than :data:`MIN_TEXT_CHARS`;
* keep the first record per ``url``.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Any

from moroccan_crawler.domain.models import PageRecord

MIN_TEXT_CHARS = 80
_WHITESPACE = re.compile(r"\s+")

# Preserve collection time through cleaning; cleaning is not a new crawl.
FIELDS = (
    "url",
    "canonical_url",
    "title",
    "text",
    "language",
    "source_domain",
    "document_type",
    "source_feed_url",
    "published_at",
    "crawled_at",
)


def to_records(pages: list[PageRecord]) -> list[dict[str, Any]]:
    return [{field: page.model_dump(mode="json")[field] for field in FIELDS} for page in pages]


def to_pages(records: list[dict[str, Any]]) -> list[PageRecord]:
    return [
        PageRecord(**{field: record[field] for field in FIELDS if field in record})
        for record in records
    ]


def _normalize(record: dict[str, Any]) -> dict[str, Any]:
    text = _WHITESPACE.sub(" ", str(record.get("text", ""))).strip()
    return {
        **{
            field: record[field]
            for field in ("canonical_url", "source_feed_url", "published_at", "crawled_at")
            if record.get(field) is not None
        },
        "url": str(record.get("url", "")).strip(),
        "title": _WHITESPACE.sub(" ", str(record.get("title", ""))).strip(),
        "text": text,
        "language": str(record.get("language", "other")),
        "source_domain": str(record.get("source_domain", "")).strip().lower(),
        "document_type": str(record.get("document_type", "html")),
        "text_chars": len(text),
    }


def etl_local(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pure-Python reference implementation of the ETL rules."""
    seen: set[str] = set()
    cleaned: list[dict[str, Any]] = []
    for record in records:
        item = _normalize(record)
        if item["text_chars"] < MIN_TEXT_CHARS or item["url"] in seen:
            continue
        seen.add(item["url"])
        cleaned.append(item)
    return cleaned


def spark_available() -> bool:
    try:
        import pyspark  # noqa: F401
    except ImportError:
        return False
    return True


def etl_spark(
    records: list[dict[str, Any]], spark: Any | None = None, master: str = "local[*]"
) -> list[dict[str, Any]]:
    """Spark implementation of the same rules; returns plain dicts.

    ``master`` allows pointing at a standalone cluster (e.g.
    ``spark://spark-master:7077``); it is ignored when a session is supplied.
    """
    from pyspark.sql import SparkSession, Window
    from pyspark.sql import functions as F

    if not records:
        return []
    # Use the active virtualenv instead of Windows' Microsoft Store python alias.
    # Explicit cluster interpreter configuration still takes precedence.
    os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
    owns_session = spark is None
    session = spark or (
        SparkSession.builder.appName("moroccan-business-etl").master(master).getOrCreate()
    )
    frame = session.createDataFrame(
        [{**_normalize(record), "_position": index} for index, record in enumerate(records)]
    )
    cleaned = (
        frame.filter(F.col("text_chars") >= MIN_TEXT_CHARS)
        .withColumn("_rank", F.row_number().over(Window.partitionBy("url").orderBy("_position")))
        .filter(F.col("_rank") == 1)
        .orderBy("_position")
        .drop("_rank", "_position")
    )
    rows = [row.asDict() for row in cleaned.collect()]
    if owns_session:
        session.stop()
    return rows


def run_etl(
    pages: list[PageRecord],
    use_spark: bool = False,
    spark: Any | None = None,
    master: str = "local[*]",
) -> list[PageRecord]:
    """Run the ETL stage, choosing the Spark or Python engine."""
    records = to_records(pages)
    use_spark = use_spark and spark_available()
    cleaned = etl_spark(records, spark, master) if use_spark else etl_local(records)
    return to_pages(cleaned)
