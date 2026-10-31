from __future__ import annotations

from typing import ClassVar

from moroccan_crawler.spiders.moroccan_pages import MoroccanPagesSpider


class BusinessSourcesSpider(MoroccanPagesSpider):
    """Crawl explicit authorized business URLs, including PDF and feed sources."""

    name = "business_sources"
    custom_settings: ClassVar[dict[str, object]] = {
        "ROBOTSTXT_OBEY": True,
        "DOWNLOAD_DELAY": 1.0,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 2,
        "FEEDS": {"data/pages.jsonl": {"format": "jsonlines", "overwrite": True}},
    }

    def __init__(self, start_urls_csv: str | None = None, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.start_urls = [url.strip() for url in (start_urls_csv or "").split(",") if url.strip()]

    # MoroccanPagesSpider.parse already performs content-type dispatch,
    # provenance capture, PDF extraction, RSS handling and bounded link follow.
