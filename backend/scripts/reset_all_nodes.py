#!/usr/bin/env python3
"""
Reset all infrastructure nodes to 'healthy' status.
Useful before running disaster recovery simulations.
"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path so we can import db modules
sys.path.insert(0, str(Path(__file__).parent.parent))

import structlog
from db.neo4j_client import Neo4jClient
from settings import Settings

log = structlog.get_logger()


async def reset_all_nodes():
    """Reset all InfraNodes to healthy status."""
    settings = Settings()
    neo4j = Neo4jClient(settings)

    try:
        await neo4j.connect()
        log.info("connected_to_neo4j", uri=settings.neo4j_uri)

        # Reset all nodes to healthy
        query = """
        MATCH (n:InfraNode)
        SET n.status = 'healthy'
        RETURN count(n) as reset_count
        """
        result = await neo4j.run(query)

        if result:
            reset_count = result[0].get("reset_count", 0)
            print(f"\n[OK] Reset {reset_count} nodes to 'healthy' status\n")
            log.info("reset_complete", count=reset_count)
            return reset_count
        else:
            print("\n[WARN] No nodes found in graph\n")
            return 0

    except Exception as e:
        print(f"\n[ERROR] {e}\n")
        log.error("reset_failed", error=str(e))
        return -1
    finally:
        await neo4j.close()


if __name__ == "__main__":
    result = asyncio.run(reset_all_nodes())
    sys.exit(0 if result >= 0 else 1)
