from __future__ import annotations

import hashlib
import json
import uuid
from collections import defaultdict

from moroccan_crawler.config import Settings
from moroccan_crawler.domain.models import GraphSnapshot


class Neo4jGraphStore:
    """Optional Neo4j persistence adapter; in-memory storage remains the default."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        if not all(
            (self.settings.neo4j_uri, self.settings.neo4j_username, self.settings.neo4j_password)
        ):
            raise ValueError("Neo4j requires NEO4J_URI, NEO4J_USERNAME, and NEO4J_PASSWORD")
        from neo4j import GraphDatabase

        self.driver = GraphDatabase.driver(
            self.settings.neo4j_uri,
            auth=(self.settings.neo4j_username, self.settings.neo4j_password),
        )

    def close(self) -> None:
        self.driver.close()

    def ensure_schema(self) -> None:
        """Create the uniqueness constraint and lookup indexes the graph relies on."""
        with self.driver.session() as session:
            session.run("DROP CONSTRAINT entity_id IF EXISTS")
            session.run(
                "CREATE CONSTRAINT entity_graph_key IF NOT EXISTS "
                "FOR (n:Entity) REQUIRE n.graph_key IS UNIQUE"
            )
            session.run("CREATE INDEX entity_name IF NOT EXISTS FOR (n:Entity) ON (n.name)")
            session.run("CREATE INDEX entity_type IF NOT EXISTS FOR (n:Entity) ON (n.type)")

    def write_snapshot(self, snapshot: GraphSnapshot) -> None:
        generation = uuid.uuid4().hex
        self.stage_snapshot(snapshot, generation)
        self.activate_generation(generation)

    def stage_snapshot(self, snapshot: GraphSnapshot, generation: str) -> None:
        """Write a complete isolated generation without changing live readers."""
        self.ensure_schema()
        with self.driver.session() as session:
            session.run(
                "UNWIND $nodes AS row "
                "MERGE (n:Entity {graph_key: row.graph_key}) "
                "SET n.id = row.id, n.generation = $generation, n.name = row.name, "
                "n.type = row.label, n += row.properties",
                generation=generation,
                nodes=[
                    {
                        "graph_key": f"{generation}:{node.id}",
                        "id": node.id,
                        "name": node.name,
                        "label": node.label,
                        "properties": node.properties,
                    }
                    for node in snapshot.nodes
                ],
            ).consume()
            grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
            for edge in snapshot.edges:
                edge_key = hashlib.sha256(
                    (
                        f"{generation}\x00{edge.source}\x00{edge.relation}\x00{edge.target}\x00"
                        + json.dumps(edge.properties, sort_keys=True, ensure_ascii=False)
                    ).encode()
                ).hexdigest()
                grouped[edge.relation.replace("`", "")].append(
                    {
                        "edge_key": edge_key,
                        "source": f"{generation}:{edge.source}",
                        "target": f"{generation}:{edge.target}",
                        "properties": edge.properties,
                    }
                )
            for relation, edges in grouped.items():
                session.run(
                    f"UNWIND $edges AS row MATCH (a:Entity {{graph_key: row.source}}), "
                    f"(b:Entity {{graph_key: row.target}}) "
                    f"MERGE (a)-[r:`{relation}` {{edge_key: row.edge_key}}]->(b) "
                    "SET r.generation = $generation, r += row.properties",
                    generation=generation,
                    edges=edges,
                ).consume()

    def activate_generation(self, generation: str) -> None:
        """Single transactional pointer update publishes the staged graph."""
        with self.driver.session() as session:
            session.run(
                "MERGE (m:GraphState {name: 'active'}) "
                "SET m.generation = $generation, m.activated_at = datetime()",
                generation=generation,
            ).consume()

    def active_generation(self) -> str | None:
        with self.driver.session() as session:
            record = session.run(
                "MATCH (m:GraphState {name: 'active'}) RETURN m.generation AS generation"
            ).single()
            return str(record["generation"]) if record and record["generation"] else None

    def count_generation(self, generation: str) -> tuple[int, int]:
        with self.driver.session() as session:
            nodes = session.run(
                "MATCH (n:Entity {generation: $generation}) RETURN count(n) AS count",
                generation=generation,
            ).single()["count"]
            edges = session.run(
                "MATCH (:Entity {generation: $generation})-[r]->"
                "(:Entity {generation: $generation}) RETURN count(r) AS count",
                generation=generation,
            ).single()["count"]
            return int(nodes), int(edges)

    def sector_counts(self) -> list[dict[str, int | str]]:
        with self.driver.session() as session:
            return [
                dict(record)
                for record in session.run(
                    "MATCH (m:GraphState {name: 'active'}), (n:Entity {type: 'Sector'}) "
                    "WHERE n.generation = m.generation "
                    "RETURN n.name AS sector, count(n) AS count ORDER BY count DESC"
                )
            ]

    @staticmethod
    def _write_node(
        tx,
        generation: str,
        label: str,
        node_id: str,
        name: str,
        properties: dict,
    ) -> None:
        tx.run(
            "MERGE (n:Entity {graph_key: $graph_key}) "
            "SET n.id = $id, n.generation = $generation, n.name = $name, "
            "n.type = $label, n += $properties",
            graph_key=f"{generation}:{node_id}",
            id=node_id,
            generation=generation,
            name=name,
            label=label,
            properties=properties,
        )

    @staticmethod
    def _write_edge(
        tx,
        generation: str,
        source: str,
        relation: str,
        target: str,
        properties: dict,
    ) -> None:
        safe_relation = relation.replace("`", "")
        tx.run(
            f"MATCH (a:Entity {{graph_key: $source}}), "
            f"(b:Entity {{graph_key: $target}}) "
            f"MERGE (a)-[r:`{safe_relation}` {{generation: $generation}}]->(b) "
            "SET r += $properties",
            source=f"{generation}:{source}",
            target=f"{generation}:{target}",
            generation=generation,
            properties=properties,
        )
