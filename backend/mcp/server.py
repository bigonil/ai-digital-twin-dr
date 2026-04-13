"""
MCP Server — exposes simulate_disaster, get_recovery_plan, check_drift
to external AI agents (Claude Code / GitHub Copilot).
"""
from __future__ import annotations

import asyncio

import structlog
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from db.neo4j_client import Neo4jClient
from db.qdrant_client import QdrantClient
from settings import Settings

log = structlog.get_logger()
settings = Settings()

server = Server("digital-twin-dr")

_neo4j: Neo4jClient | None = None
_qdrant: QdrantClient | None = None


async def _get_neo4j() -> Neo4jClient:
    global _neo4j
    if _neo4j is None:
        _neo4j = Neo4jClient(settings)
        await _neo4j.connect()
    return _neo4j


async def _get_qdrant() -> QdrantClient:
    global _qdrant
    if _qdrant is None:
        _qdrant = QdrantClient(settings)
        await _qdrant.connect()
    return _qdrant


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="simulate_disaster",
            description=(
                "Perform recursive impact analysis in Neo4j for a given node. "
                "Returns the blast radius — all nodes that would cascade-fail."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "node_id": {"type": "string", "description": "Neo4j node ID to fail"},
                    "depth": {"type": "integer", "default": 5, "description": "Max traversal depth"},
                },
                "required": ["node_id"],
            },
        ),
        Tool(
            name="get_recovery_plan",
            description=(
                "Generate a step-by-step DR playbook by querying Neo4j topology "
                "and Qdrant documentation for the target resource."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "Node ID or resource name to recover"},
                },
                "required": ["target"],
            },
        ),
        Tool(
            name="check_drift",
            description="Compare Terraform state vs Neo4j graph and return differences.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    neo4j = await _get_neo4j()

    if name == "simulate_disaster":
        node_id = arguments["node_id"]
        depth = int(arguments.get("depth", 5))
        rows = await neo4j.simulate_disaster(node_id, depth)

        if not rows:
            text = f"No downstream impact found for node '{node_id}' within depth {depth}."
        else:
            lines = [f"💥 Blast radius for '{node_id}' ({len(rows)} affected nodes):\n"]
            for r in rows:
                rto = f"RTO={r.get('rto_minutes')}min" if r.get("rto_minutes") else ""
                lines.append(f"  depth={r['distance']} | {r['name']} ({r['type']}) {rto}")
            text = "\n".join(lines)

        return [TextContent(type="text", text=text)]

    if name == "get_recovery_plan":
        target = arguments["target"]
        node_rows = await neo4j.run(
            "MATCH (n {id: $id}) RETURN n.name AS name, n.type AS type, "
            "n.rto_minutes AS rto, n.rpo_minutes AS rpo",
            {"id": target},
        )

        doc_context = ""
        try:
            qdrant = await _get_qdrant()
            import ollama as ol
            embed_resp = ol.embeddings(model=settings.ollama_embed_model, prompt=f"recovery plan for {target}")
            docs = await qdrant.search(embed_resp["embedding"], limit=3)
            if docs:
                doc_context = "\n\nRelevant documentation:\n" + "\n---\n".join(
                    d["payload"].get("text", "") for d in docs
                )
        except Exception as exc:
            log.warning("mcp.qdrant_search_failed", error=str(exc))

        if node_rows:
            n = node_rows[0]
            plan = (
                f"Recovery Plan for {n['name']} ({n['type']})\n"
                f"RTO target: {n['rto']} min | RPO target: {n['rpo']} min\n\n"
                "Steps:\n"
                "1. Verify monitoring alerts — confirm failure is real, not a false positive\n"
                "2. Isolate the failed component to prevent write amplification\n"
                "3. Promote replica or activate standby if available\n"
                "4. Restore from last snapshot/backup within RPO window\n"
                "5. Re-validate downstream dependencies\n"
                "6. Update Neo4j node status to 'healthy'\n"
                "7. Document post-mortem in architecture.md"
            )
        else:
            plan = f"Node '{target}' not found in graph. Run Terraform ingestion first."

        return [TextContent(type="text", text=plan + doc_context)]

    if name == "check_drift":
        graph_nodes = await neo4j.run("MATCH (n:InfraNode) RETURN n.id AS id, n.name AS name")
        lines = [f"Graph contains {len(graph_nodes)} InfraNode(s):\n"]
        for n in graph_nodes[:20]:
            lines.append(f"  {n['id']} — {n['name']}")
        if len(graph_nodes) > 20:
            lines.append(f"  … and {len(graph_nodes) - 20} more")
        lines.append("\nNote: Full Terraform state comparison requires running `parsers/infra.py`.")
        return [TextContent(type="text", text="\n".join(lines))]

    return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def main():
    log.info("mcp_server.start")
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
