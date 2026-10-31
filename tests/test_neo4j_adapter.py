import pytest

from moroccan_crawler.config import Settings
from moroccan_crawler.graph.neo4j_store import Neo4jGraphStore


def test_neo4j_adapter_requires_configuration() -> None:
    with pytest.raises(ValueError):
        Neo4jGraphStore(
            Settings(
                _env_file=None,
                neo4j_enabled=True,
                neo4j_uri=None,
                neo4j_username=None,
                neo4j_password=None,
            )
        )
