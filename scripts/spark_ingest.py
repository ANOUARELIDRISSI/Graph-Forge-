"""Big-data entry point; use Docker/Linux for Parquet output, Windows for JSON export."""

import json
import os
from pathlib import Path

from pyspark.sql import SparkSession


def main() -> None:
    spark = SparkSession.builder.appName("moroccan-business-ingestion").getOrCreate()
    documents = spark.read.json("data/pages.jsonl")
    from pyspark.sql import functions as F

    cleaned = (
        documents.withColumn("title", F.trim(F.regexp_replace("title", r"\\s+", " ")))
        .withColumn("text", F.trim(F.regexp_replace("text", r"\\s+", " ")))
        .withColumn("source_domain", F.lower(F.trim("source_domain")))
        .withColumn("text_chars", F.length("text"))
        .withColumn(
            "quality",
            F.when(F.col("url").startswith("http"), 20).otherwise(4)
            + F.when(F.col("text_chars") >= 500, 30).otherwise(10),
        )
        .dropDuplicates(["url"])
        .filter(F.col("text_chars") >= 80)
    )
    cleaned.select("url", "title", "language", "source_domain", "text_chars", "quality").show(
        20, truncate=False
    )
    output = Path("data/spark")
    output.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        rows = [row.asDict() for row in cleaned.collect()]
        (output / "pages.json").write_text(
            json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"Spark ETL complete: {len(rows)} cleaned rows written to {output / 'pages.json'}")
    else:
        cleaned.write.mode("overwrite").parquet(str(output / "pages"))
        print(f"Spark ETL complete: Parquet written to {output / 'pages'}")
    spark.stop()


if __name__ == "__main__":
    main()
