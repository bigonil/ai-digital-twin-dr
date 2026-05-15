"""Neo4j async driver wrapper."""
import json
import re
from typing import Any, List, Dict

import structlog
from neo4j import AsyncGraphDatabase

log = structlog.get_logger()

# Whitelist of allowed relationship types to prevent Cypher injection
_ALLOWED_REL_TYPES: frozenset[str] = frozenset(
    {"DEPENDS_ON", "INTERACTS_WITH", "DOCUMENTED_BY", "STORES_IN", "READS_FROM", "WRITES_TO", "DEPLOYED_ON"}
)

# Valid node-id pattern: alphanumeric, underscores, hyphens, dots (no special chars)
_NODE_ID_RE = re.compile(r"^[\w\-\.]+$")

CONSTRAINTS = [
    "CREATE CONSTRAINT infra_node_id IF NOT EXISTS FOR (n:InfraNode) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT function_id IF NOT EXISTS FOR (n:Function) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT document_id IF NOT EXISTS FOR (n:Document) REQUIRE n.id IS UNIQUE",
]

INDEXES = [
    "CREATE INDEX infra_type IF NOT EXISTS FOR (n:InfraNode) ON (n.type)",
    "CREATE INDEX infra_region IF NOT EXISTS FOR (n:InfraNode) ON (n.region)",
    "CREATE INDEX infra_status IF NOT EXISTS FOR (n:InfraNode) ON (n.status)",
    "CREATE INDEX infra_recovery_strategy IF NOT EXISTS FOR (n:InfraNode) ON (n.recovery_strategy)",
    "CREATE INDEX infra_monitoring_state IF NOT EXISTS FOR (n:InfraNode) ON (n.monitoring_state)",
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
        props = {
            k: (json.dumps(v) if isinstance(v, (dict, list)) else v)
            for k, v in node.items()
            if k != "id"
        }
        await self.run(query, {"id": node["id"], "props": props})

    async def merge_edge(self, source: str, target: str, rel_type: str, props: dict | None = None) -> None:
        if rel_type not in _ALLOWED_REL_TYPES:
            raise ValueError(f"Disallowed relationship type: {rel_type!r}. Must be one of {sorted(_ALLOWED_REL_TYPES)}")
        query = f"""
        MATCH (a {{id: $source}}), (b {{id: $target}})
        MERGE (a)-[r:{rel_type}]->(b)
        SET r += $props
        """
        await self.run(query, {"source": source, "target": target, "props": props or {}})

    async def get_topology(self) -> dict[str, Any]:
        nodes = await self.run(
            "MATCH (n:InfraNode) RETURN n.id AS id, n.name AS name, n.type AS type, "
            "n.status AS status, n.provider AS provider, n.region AS region, "
            "n.is_redundant AS is_redundant, n.rto_minutes AS rto_minutes, "
            "n.rpo_minutes AS rpo_minutes, labels(n) AS labels"
        )
        edges = await self.run(
            "MATCH (a:InfraNode)-[r]->(b:InfraNode) RETURN a.id AS source, b.id AS target, type(r) AS type, r.weight AS weight"
        )
        return {"nodes": nodes, "edges": edges}

    async def simulate_disaster(self, node_id: str, depth: int = 5) -> list[dict]:
        depth = max(1, min(depth, 10))  # clamp to safe range
        # BFS to find all nodes affected by a cascading failure
        # Follow BOTH directions: upstream dependencies AND downstream dependents
        query = f"""
        MATCH path = (origin {{id: $node_id}})-[*1..{depth}]-(affected)
        WHERE origin <> affected
        WITH affected, MIN(length(path)) AS dist
        RETURN affected.id AS id, affected.name AS name, affected.type AS type,
               affected.rto_minutes AS rto_minutes, affected.rpo_minutes AS rpo_minutes,
               dist AS distance
        ORDER BY dist
        """
        return await self.run(query, {"node_id": node_id})

    async def get_outgoing_edges(self, node_id: str) -> List[Dict[str, Any]]:
        """
        Get all outgoing edges from a node.

        Returns: [{"target": node_id, "type": edge_type, "latency_ms": ..., "shares_resource": ..., "contention_factor": ...}]
        """
        query = """
        MATCH (n:InfraNode {id: $node_id})-[r]->(target:InfraNode)
        RETURN target.id as target, type(r) as type,
               r.latency_ms as latency_ms, r.shares_resource as shares_resource,
               r.contention_factor as contention_factor
        """
        result = await self.run(query, {"node_id": node_id})
        return result

    async def get_node_details(self, node_id: str) -> Dict[str, Any]:
        """
        Get all details for a single node.

        Returns: {id, name, type, rto_minutes, rpo_minutes, recovery_strategy, monitoring_state, ...}
        """
        query = """
        MATCH (n:InfraNode {id: $node_id})
        RETURN n
        """
        result = await self.run(query, {"node_id": node_id})
        if not result:
            return None

        node = result[0].get("n")
        if not node:
            return None

        return {
            "id": node.get("id"),
            "name": node.get("name"),
            "type": node.get("type"),
            "rto_minutes": node.get("rto_minutes"),
            "rpo_minutes": node.get("rpo_minutes"),
            "recovery_strategy": node.get("recovery_strategy", "generic"),
            "monitoring_state": node.get("monitoring_state", "unknown"),
            "observed_latency_ms": node.get("observed_latency_ms"),
        }

    async def get_replicas(self, node_id: str) -> List[Dict[str, Any]]:
        """
        Get all replica nodes connected via REPLICATES_TO edge.

        Returns: [{"id": replica_id, "name": name, "rto_minutes": rto, ...}]
        """
        query = """
        MATCH (n:InfraNode {id: $node_id})-[r:REPLICATES_TO]->(replica:InfraNode)
        RETURN replica.id as id, replica.name as name, replica.type as type,
               replica.rto_minutes as rto_minutes, replica.rpo_minutes as rpo_minutes,
               replica.recovery_strategy as recovery_strategy,
               replica.monitoring_state as monitoring_state
        """
        return await self.run(query, {"node_id": node_id})
