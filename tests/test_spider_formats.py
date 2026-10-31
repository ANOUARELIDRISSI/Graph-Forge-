from types import SimpleNamespace

import scrapy
from scrapy.http import HtmlResponse, XmlResponse

from moroccan_crawler.spiders.moroccan_pages import MoroccanPagesSpider


def test_rss_entries_preserve_feed_provenance_and_follow_article() -> None:
    body = b"""<?xml version="1.0"?>
    <rss version="2.0"><channel><item>
      <title>Rapport sur les entreprises marocaines</title>
      <link>https://www.hcp.ma/article-economie.html</link>
      <pubDate>Fri, 30 Oct 2026 10:00:00 GMT</pubDate>
      <description>Le rapport analyse la croissance, l'emploi et l'investissement des entreprises au Maroc pour la nouvelle periode.</description>
    </item></channel></rss>"""
    response = XmlResponse(
        url="https://www.hcp.ma/xml/syndication.rss",
        body=body,
        encoding="utf-8",
        headers={"Content-Type": "application/rss+xml"},
    )
    results = list(MoroccanPagesSpider().parse(response))
    record = next(item for item in results if isinstance(item, dict))
    request = next(item for item in results if isinstance(item, scrapy.Request))
    assert record["document_type"] == "rss"
    assert record["source_feed_url"] == response.url
    assert record["canonical_url"] == "https://www.hcp.ma/article-economie.html"
    assert record["published_at"].startswith("2026-10-30T10:00:00")
    assert request.url == record["canonical_url"]


def test_html_discovers_pdf_and_feed_links() -> None:
    response = HtmlResponse(
        url="https://example.ma/economie",
        body=b"""<html><head><title>Economie</title>
        <link rel="alternate" type="application/rss+xml" href="/feed.xml" />
        </head><body><main>Une analyse economique marocaine suffisamment longue pour etre indexee par le crawler et testee.</main>
        <a href="/rapport-annuel.pdf">Rapport</a></body></html>""",
        encoding="utf-8",
    )
    results = list(MoroccanPagesSpider().parse(response))
    requests = [item.url for item in results if isinstance(item, scrapy.Request)]
    assert "https://example.ma/feed.xml" in requests
    assert "https://example.ma/rapport-annuel.pdf" in requests


def test_pdf_text_is_extracted(monkeypatch) -> None:
    reader = SimpleNamespace(
        pages=[SimpleNamespace(extract_text=lambda: "Rapport financier Maroc " * 20)],
        metadata=SimpleNamespace(title="Rapport annuel"),
    )
    monkeypatch.setattr(
        "moroccan_crawler.spiders.moroccan_pages.PdfReader", lambda stream: reader
    )
    response = HtmlResponse(
        url="https://example.ma/rapport.pdf",
        body=b"%PDF-mocked",
        headers={"Content-Type": "application/pdf"},
    )
    records = list(MoroccanPagesSpider().parse(response))
    assert records[0]["document_type"] == "pdf"
    assert records[0]["title"] == "Rapport annuel"
    assert len(records[0]["text"]) >= 200
