from __future__ import annotations

from moroccan_crawler.domain.models import PageRecord, TextChunk


def chunk_page(page: PageRecord, size: int = 800, overlap: int = 120) -> list[TextChunk]:
    """Split a heterogeneous document into bounded, provenance-preserving chunks."""
    if size <= overlap:
        raise ValueError("size must be greater than overlap")
    chunks: list[TextChunk] = []
    step = size - overlap
    for index, start in enumerate(range(0, max(len(page.text), 1), step)):
        text = page.text[start : start + size].strip()
        if not text:
            continue
        chunks.append(
            TextChunk(
                id=f"{page.url}#chunk-{index}",
                document_id=str(page.url),
                index=index,
                text=text,
                source_url=page.canonical_url or page.url,
                language=page.language,
            )
        )
    return chunks
