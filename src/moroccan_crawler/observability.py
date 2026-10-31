from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager


def _langfuse_enabled() -> bool:
    """Monitoring is opt-in: honour the LANGFUSE_ENABLED configuration flag."""
    try:
        from moroccan_crawler.config import Settings

        return Settings().langfuse_enabled
    except (ImportError, ValueError):
        return False


@contextmanager
def observe_generation(name: str, model: str, input_data: object) -> Iterator[object]:
    """Send optional Langfuse generation telemetry without making it required locally."""
    if not _langfuse_enabled():
        yield None
        return
    try:
        from langfuse import get_client

        langfuse = get_client()
        with langfuse.start_as_current_observation(
            as_type="generation", name=name, model=model, input=input_data
        ) as generation:
            yield generation
        langfuse.flush()
    except (ImportError, RuntimeError, TypeError, ValueError):
        yield None
