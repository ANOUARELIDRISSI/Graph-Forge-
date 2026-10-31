from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# Canonical surface forms for the aliases that appear in Moroccan business text.
# Keys are folded (accent-free, casefolded) so "Automobile" and "automobile"
# both resolve to the same sector node.
_ALIASES: dict[str, str] = {
    "automobile": "automotive",
    "car": "automotive",
    "tourisme": "tourism",
    "tourist": "tourism",
    "agro": "agriculture",
    "agroalimentaire": "agriculture",
    "banque": "finance",
    "banking": "finance",
    "maroc": "morocco",
    "royaume": "morocco",
    "casablanca settat": "casablanca-settat",
    "tanger tetouan": "tanger-tetouan",
    "rabat sale kenitra": "rabat-sale-kenitra",
}

_TYPE_LABELS: dict[str, str] = {
    "sector": "Sector",
    "country": "Country",
    "region": "Region",
    "organization": "Organization",
    "entity": "Entity",
}


@dataclass(frozen=True, slots=True)
class ResolvedEntity:
    """A canonicalised entity identity shared by every alias it was seen as."""

    id: str
    name: str
    entity_type: str
    key: str


def fold(text: str) -> str:
    """Normalise Arabic/Latin text into a stable comparison key."""
    decomposed = unicodedata.normalize("NFKD", text)
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    lowered = without_marks.casefold()
    collapsed = re.sub(r"[^\w\s-]", " ", lowered, flags=re.UNICODE)
    return re.sub(r"\s+", " ", collapsed).strip()


def resolve(name: str, entity_type: str = "Entity") -> ResolvedEntity:
    """Map an extracted mention to a deduplicated, canonical graph identity."""
    label = _TYPE_LABELS.get(entity_type.strip().casefold(), "Entity")
    canonical = _ALIASES.get(fold(name), fold(name)) or fold(name)
    display = canonical.title() if canonical else name.strip()
    return ResolvedEntity(
        id=f"{label.casefold()}:{canonical}",
        name=display,
        entity_type=label,
        key=f"{label.casefold()}:{canonical}",
    )
