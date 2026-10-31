from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from io import BytesIO
from typing import ClassVar
from urllib.parse import urlparse

import scrapy
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from moroccan_crawler.parsing import detect_language, normalize_text, source_domain


class MoroccanPagesSpider(scrapy.Spider):
    """Crawl explicitly supplied pages and emit provenance-rich records.

    Use `-a start_urls_csv=...` with authorized URLs. The default URL is the
    Scrapy tutorial site so the crawler can be tested without targeting a
    Moroccan website or collecting personal data.
    """

    name = "moroccan_pages"
    allowed_domains: ClassVar[list[str]] = []
    custom_settings: ClassVar[dict[str, object]] = {
        "ROBOTSTXT_OBEY": True,
        "DOWNLOAD_DELAY": 1.0,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 2,
        "USER_AGENT": "MoroccanBusinessGraph/1.0 (public research crawler)",
        "DOWNLOAD_TIMEOUT": 30,
        "DEPTH_LIMIT": 1,
        "CLOSESPIDER_PAGECOUNT": 35,
        "RETRY_TIMES": 2,
        "LOG_LEVEL": "INFO",
        "TELNETCONSOLE_ENABLED": False,
    }

    def __init__(self, start_urls_csv: str | None = None, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.start_urls = [
            url.strip()
            for url in (start_urls_csv or "https://quotes.toscrape.com/").split(",")
            if url.strip()
        ]
        self.allowed_domains = [urlparse(url).netloc for url in self.start_urls]

    def parse(self, response: scrapy.http.Response):
        if self._is_pdf(response):
            try:
                reader = PdfReader(BytesIO(response.body))
                text = normalize_text([page.extract_text() or "" for page in reader.pages[:100]])
            except (PdfReadError, ValueError, OSError) as error:
                self.logger.warning("PDF extraction failed for %s: %s", response.url, error)
                return
            if len(text) >= 200:
                yield {
                    "url": response.url,
                    "title": str(reader.metadata.title or response.url)
                    if reader.metadata
                    else response.url,
                    "text": text,
                    "language": detect_language(text),
                    "country_context": "Morocco",
                    "source_domain": source_domain(response.url),
                    "document_type": "pdf",
                    "crawled_at": datetime.now(UTC).isoformat(),
                }
            return
        if self._is_feed(response):
            yield from self.parse_feed(response)
            return
        title = response.css("title::text").get(default="").strip()
        blocks = response.css("article, main, [role=main]")
        text = normalize_text(
            (blocks if blocks else response.css("body"))
            .xpath(
                ".//text()[not(ancestor::script or ancestor::style or ancestor::nav or ancestor::footer or ancestor::header)]"
            )
            .getall()
        )
        if len(text) >= 200:
            yield {
                "url": response.url,
                "title": title,
                "text": text,
                "language": detect_language(text),
                "country_context": "Morocco",
                "source_domain": source_domain(response.url),
                "crawled_at": datetime.now(UTC).isoformat(),
            }
        # Unit tests and callers may construct a standalone Response without a
        # Request; Scrapy's ``Response.meta`` property raises in that case.
        try:
            depth = response.meta.get("depth", 0)
        except AttributeError:
            depth = 0
        if depth == 0:
            links = response.css("a::attr(href)").getall()
            links.extend(
                response.css(
                    'link[rel~="alternate"][type*="rss"]::attr(href), '
                    'link[rel~="alternate"][type*="atom"]::attr(href)'
                ).getall()
            )
            for href in links:
                url = response.urljoin(href).split("#", 1)[0]
                if (
                    urlparse(url).hostname == urlparse(response.url).hostname
                    and (
                        url.lower().endswith((".pdf", ".rss", ".xml", "/feed", "/feeds"))
                        or any(
                            word in url.lower()
                            for word in (
                                "entreprise",
                                "economie",
                                "statistique",
                                "financier",
                                "rapport",
                                "rss",
                            )
                        )
                    )
                    and not url.lower().endswith((".zip", ".xlsx"))
                ):
                    yield response.follow(url, self.parse)

    def parse_feed(self, response: scrapy.http.Response):
        """Emit provenance-rich RSS/Atom entries and follow their canonical pages."""
        selector = scrapy.Selector(text=response.text, type="xml")
        selector.remove_namespaces()
        for item in selector.xpath("//item | //entry"):
            title = normalize_text(item.xpath("./title//text()").getall())
            link = (
                item.xpath("./link/@href").get()
                or item.xpath("string(./link)").get()
                or item.xpath("string(./guid)").get()
                or ""
            ).strip()
            canonical = response.urljoin(link) if link else response.url
            fragments = item.xpath(
                "./description//text() | ./summary//text() | ./content//text()"
            ).getall()
            raw_text = normalize_text(fragments)
            if "<" in raw_text and ">" in raw_text:
                raw_text = normalize_text(
                    scrapy.Selector(text=raw_text).xpath("//text()").getall()
                )
            text = normalize_text([title, raw_text])
            if len(text) < 80:
                continue
            entry_key = hashlib.sha256(
                f"{canonical}\x00{title}".encode()
            ).hexdigest()[:20]
            published = self._published_at(
                item.xpath("string(./pubDate)").get()
                or item.xpath("string(./published)").get()
                or item.xpath("string(./updated)").get()
            )
            yield {
                "url": f"{response.url}#entry-{entry_key}",
                "canonical_url": canonical,
                "title": title or canonical,
                "text": text,
                "language": detect_language(text),
                "country_context": "Morocco",
                "source_domain": source_domain(canonical),
                "document_type": "rss",
                "source_feed_url": response.url,
                "published_at": published,
                "crawled_at": datetime.now(UTC).isoformat(),
            }
            if (
                canonical.startswith(("http://", "https://"))
                and urlparse(canonical).hostname == urlparse(response.url).hostname
                and canonical != response.url
            ):
                yield response.follow(canonical, self.parse)

    @staticmethod
    def _is_pdf(response: scrapy.http.Response) -> bool:
        content_type = response.headers.get("Content-Type", b"").decode(
            "latin-1", errors="ignore"
        )
        return response.body.startswith(b"%PDF-") or "application/pdf" in content_type.lower()

    @staticmethod
    def _is_feed(response: scrapy.http.Response) -> bool:
        content_type = response.headers.get("Content-Type", b"").decode(
            "latin-1", errors="ignore"
        )
        prefix = response.body.lstrip()[:300].lower()
        return (
            any(token in content_type.lower() for token in ("rss", "atom", "xml"))
            and (b"<rss" in prefix or b"<feed" in prefix)
        ) or prefix.startswith((b"<rss", b"<feed"))

    @staticmethod
    def _published_at(value: str | None) -> str | None:
        if not value:
            return None
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            try:
                parsed = datetime.fromisoformat(value)
            except ValueError:
                return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC).isoformat()
