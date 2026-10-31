from dataclasses import dataclass


@dataclass(slots=True)
class PageRecord:
    url: str
    title: str
    text: str
    language: str
    country_context: str
    source_domain: str
