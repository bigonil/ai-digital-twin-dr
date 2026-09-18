#!/usr/bin/env python3
"""
Ingest documentation into Qdrant and link to Neo4j infrastructure nodes.
Chunks markdown files, embeds via Ollama, stores in Qdrant, creates Document nodes in Neo4j.
"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path so we can import db modules
sys.path.insert(0, str(Path(__file__).parent.parent))

import structlog
from db.neo4j_client import Neo4jClient
from db.qdrant_client import QdrantClient
from parsers.docs import ingest
from settings import Settings

log = structlog.get_logger()

# Mapping: document keywords → infrastructure node IDs
DOC_NODE_MAPPINGS = {
    "cloudfront": ["lb-001"],
    "cdn": ["lb-001"],
    "rds": ["db-001-primary", "db-002-replica"],
    "database": ["db-001-primary", "db-002-replica"],
    "failover": ["db-001-primary", "db-002-replica"],
    "api": ["api-001", "api-002"],
    "cache": ["cache-001"],
    "queue": ["queue-001"],
    "storage": ["storage-001"],
    "backup": ["backup-001"],
    "architecture": ["db-001-primary", "db-002-replica", "api-001", "api-002", "cache-001", "queue-001", "lb-001"],
    "dependencies": ["db-001-primary", "db-002-replica", "api-001", "api-002", "cache-001", "queue-001"],
    "topology": ["db-001-primary", "db-002-replica", "api-001", "api-002", "cache-001", "queue-001"],
    "procedures": ["db-001-primary", "db-002-replica", "backup-001"],
    "runbook": ["db-001-primary", "db-002-replica", "backup-001"],
    "scenarios": ["db-001-primary", "db-002-replica", "api-001", "api-002"],
    "faq": ["db-001-primary", "db-002-replica", "api-001", "api-002"],
}


async def create_doc_links(neo4j_client, docs_dir: Path) -> int:
    """
    Create DOCUMENTED_BY relationships between Document nodes and InfraNodes.
    Returns count of relationships created.
    """
    edge_count = 0

    # Get all Document nodes
    docs_query = "MATCH (d:Document) RETURN d.id AS id, d.source_file AS source_file"
    results = await neo4j_client.run(docs_query)

    if not results:
        log.warning("docs.no_document_nodes")
        return 0

    for doc in results:
        doc_id = doc.get("id")
        source_file = doc.get("source_file", "").lower()

        # Find matching infrastructure nodes
        target_nodes = set()
        for keyword, node_ids in DOC_NODE_MAPPINGS.items():
            if keyword in source_file:
                target_nodes.update(node_ids)

        # Create DOCUMENTED_BY relationships
        for node_id in target_nodes:
            try:
                await neo4j_client.merge_edge(
                    source=doc_id,
                    target=node_id,
                    rel_type="DOCUMENTED_BY",
                    props={"ingested_at": "now()"}
                )
                edge_count += 1
                log.info("docs.link_created", doc_id=doc_id, target_node=node_id)
            except Exception as e:
                log.warning("docs.link_failed", doc_id=doc_id, node_id=node_id, error=str(e))

    return edge_count


async def ingest_all():
    """Main ingestion pipeline."""
    settings = Settings()
    qdrant = QdrantClient(settings)
    neo4j = Neo4jClient(settings)

    docs_dir = Path(__file__).parent.parent / "docs"

    try:
        # Connect to services
        await qdrant.connect()
        await neo4j.connect()
        log.info("ingest.connected", qdrant_url=settings.qdrant_url, neo4j_uri=settings.neo4j_uri)

        # Ingest documents: chunks → Qdrant + Document nodes → Neo4j
        print("\n[INFO] Ingesting documents from docs/ directory...")
        doc_stats = await ingest(docs_dir=docs_dir, qdrant_client=qdrant, neo4j_client=neo4j)
        print(f"[OK] Documents ingested:")
        print(f"     - Qdrant points: {doc_stats['qdrant_points']}")
        print(f"     - Neo4j Document nodes: {doc_stats['neo4j_nodes']}")

        # Create relationships between Document nodes and InfraNodes
        print("[INFO] Creating DOCUMENTS relationships...")
        edge_count = await create_doc_links(neo4j, docs_dir)
        print(f"[OK] Created {edge_count} DOCUMENTS relationships")

        # Verify
        doc_count = await neo4j.run("MATCH (d:Document) RETURN COUNT(d) AS count")
        inf_count = await neo4j.run("MATCH (n:InfraNode) RETURN COUNT(n) AS count")
        edge_db_count = await neo4j.run("MATCH ()-[r:DOCUMENTED_BY]->() RETURN COUNT(r) AS count")

        print(f"\n[OK] Ingestion complete!")
        print(f"     - Documents: {doc_count[0]['count'] if doc_count else 0}")
        print(f"     - Infrastructure nodes: {inf_count[0]['count'] if inf_count else 0}")
        print(f"     - Document→Infra relationships: {edge_db_count[0]['count'] if edge_db_count else 0}")

        return True

    except Exception as e:
        print(f"\n[ERROR] {e}\n")
        log.error("ingest.failed", error=str(e))
        return False
    finally:
        await qdrant.close()
        await neo4j.close()


if __name__ == "__main__":
    success = asyncio.run(ingest_all())
    sys.exit(0 if success else 1)
