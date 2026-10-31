from __future__ import annotations

from pathlib import Path

import httpx

from moroccan_crawler.config import Settings


class RawDocumentStore:
    """Raw-zone boundary; local filesystem is the development fallback for HDFS."""

    def __init__(self, root: str = "data/raw") -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, source_name: str, content: str) -> str:
        target = self.root / source_name.replace("/", "_").replace("\\", "_")
        target.write_text(content, encoding="utf-8")
        return str(target)


class HdfsDocumentStore:
    """WebHDFS raw-zone writer.

    Talks to the namenode's WebHDFS REST API (``op=CREATE``) so no Hadoop
    client libraries are needed. If the namenode is unreachable the write
    degrades to a local :class:`RawDocumentStore` — ingestion should not be
    blocked by a missing cluster, but the fallback is recorded so it is visible.
    """

    def __init__(
        self,
        settings: Settings,
        fallback: RawDocumentStore | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = settings.hdfs_url.rstrip("/")
        self.user = settings.hdfs_user
        self.root = settings.hdfs_root.rstrip("/")
        self.fallback = fallback or RawDocumentStore(settings.hdfs_fallback_root)
        self.fell_back = False
        self.client = httpx.Client(timeout=30, transport=transport, follow_redirects=True)

    def close(self) -> None:
        self.client.close()

    def target_path(self, source_name: str) -> str:
        name = source_name.replace("/", "_").replace("\\", "_")
        return f"{self.root}/{name}"

    def put(self, source_name: str, content: str) -> str:
        target = self.target_path(source_name)
        try:
            response = self.client.put(
                f"{self.base_url}/webhdfs/v1{target}",
                params={"op": "CREATE", "overwrite": "true", "user.name": self.user},
                content=content.encode("utf-8"),
                headers={"Content-Type": "application/octet-stream"},
            )
            response.raise_for_status()
        except httpx.HTTPError:
            self.fell_back = True
            return self.fallback.put(source_name, content)
        return f"webhdfs://{self.base_url}{target}"


def build_raw_document_store(
    settings: Settings, transport: httpx.BaseTransport | None = None
) -> RawDocumentStore | HdfsDocumentStore:
    """Return the configured raw-zone store (WebHDFS when enabled)."""
    if settings.hdfs_enabled:
        return HdfsDocumentStore(settings, transport=transport)
    return RawDocumentStore(settings.hdfs_fallback_root)
