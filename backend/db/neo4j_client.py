"""Neo4j async driver wrapper."""
from typing import Any

import structlog
from neo4j import AsyncGraphDatabase

log = structlog.get_logger()

CONSTRAINTS = [
    "CREATE CONSTRAINT infra_node_id IF NOT EXISTS FOR (n:InfraNode) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT function_id IF NOT EXISTS FOR (n:Function) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT document_id IF NOT EXISTS FOR (n:Document) REQUIRE n.id IS UNIQUE",
]

INDEXES = [
    "CREATE INDEX infra_type IF NOT EXISTS FOR (n:InfraNode) ON (n.type)",
    "CREATE INDEX infra_region IF NOT EXISTS FOR (n:InfraNode) ON (n.region)",
    "CREATE INDEX infra_status IF NOT EXISTS FOR (n:InfraNode) ON (n.status)",
]


class Neo4jClient:
    def __init__(self, settings):
        self._uri = settings.neo4j_uri
        self._user = settings.neo4j_user
        self._password = settings.neo4j_password
        self._driver = None

    async def connect(self):
        self._driver = AsyncGraphDatabase.driver(
            self._uri,
            auth=(self._user, self._password),
            max_connection_pool_size=50,
        )
        await self._driver.verify_connectivity()
        await self._apply_schema()
        log.info("neo4j.connected", uri=self._uri)

    async def _apply_schema(self):
        async with self._driver.session() as session:
            for stmt in CONSTRAINTS + INDEXES:
                await session.run(stmt)

    async def close(self):
        if self._driver:
            await self._driver.close()

    async def run(self, query: str, params: dict[str, Any] | None = None) -> list[dict]:
        async with self._driver.session() as session:
            result = await session.run(query, params or {})
            return [record.data() async for record in result]

    async def merge_node(self, node: dict[str, Any], label: str = "InfraNode") -> None:
        query = f"""
        MERGE (n:{label} {{id: $id}})
        SET n += $props
        """
        props = {k: v for k, v in node.items() if k != "id"}
        await self.run(query, {"id": node["id"], "props": props})

    async def merge_edge(self, source: str, target: str, rel_type: str, props: dict | None = None) -> None:
        query = f"""
        MATCH (a {{id: $source}}), (b {{id: $target}})
        MERGE (a)-[r:{rel_type}]->(b)
        SET r += $props
        """
        await self.run(query, {"source": source, "target": target, "props": props or {}})

    async def get_topology(self) -> dict[str, Any]:
        nodes = await self.run(
            "MATCH (n) RETURN n.id AS id, n.name AS name, n.type AS type, "
            "n.status AS status, n.provider AS provider, n.region AS region, "
            "n.is_redundant AS is_redundant, n.rto_minutes AS rto_minutes, "
            "n.rpo_minutes AS rpo_minutes, labels(n) AS labels"
        )
        edges = await self.run(
            "MATCH (a)-[r]->(b) RETURN a.id AS source, b.id AS target, type(r) AS type, r.weight AS weight"
        )
        return {"nodes": nodes, "edges": edges}

    async def simulate_disaster(self, node_id: str, depth: int = 5) -> list[dict]:
        query = """
        MATCH path = (origin {id: $node_id})-[*1..$depth]->(affected)
        WHERE origin <> affected
        WITH affected, MIN(length(path)) AS dist
        RETURN affected.id AS id, affected.name AS name, affected.type AS type,
               affected.rto_minutes AS rto_minutes, affected.rpo_minutes AS rpo_minutes,
               dist AS distance
        ORDER BY dist
        """
        return await self.run(query, {"node_id": node_id, "depth": depth})
