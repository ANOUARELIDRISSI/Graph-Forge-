from __future__ import annotations

import re
from urllib.parse import urlparse

ARABIC = re.compile(r"[\u0600-\u06ff]")
FRENCH = re.compile(r"\b(le|la|les|des|une|avec|pour|dans|Maroc|marocain)\b", re.IGNORECASE)


def normalize_text(parts: list[str]) -> str:
    """Collapse HTML fragments into stable, whitespace-normalized text."""
    return re.sub(r"\s+", " ", " ".join(part.strip() for part in parts if part.strip())).strip()


def detect_language(text: str) -> str:
    """Return a lightweight label useful for routing; not a replacement for NLP detection."""
    arabic = len(ARABIC.findall(text))
    french = len(FRENCH.findall(text))
    if arabic and french:
        return "ar+fr"
    if arabic:
        return "ar"
    if french:
        return "fr"
    return "other"


def source_domain(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")
