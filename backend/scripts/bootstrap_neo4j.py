#!/usr/bin/env python3
"""
Bootstrap Neo4j with sample infrastructure for testing.
Creates a realistic AWS infrastructure graph with interdependencies.
"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path so we can import db modules
sys.path.insert(0, str(Path(__file__).parent.parent))

import structlog
from db.neo4j_client import Neo4jClient
from db.migrations.add_recovery_schema import migrate_add_recovery_schema
from settings import Settings

log = structlog.get_logger()


async def bootstrap_infrastructure():
    """Create sample infrastructure graph in Neo4j."""
    settings = Settings()
    neo4j = Neo4jClient(settings)

    try:
        await neo4j.connect()
        log.info("connected_to_neo4j", uri=settings.neo4j_uri)

        # Sample infrastructure nodes
        nodes = [
            # Primary database cluster
            {
                "id": "db-001-primary",
                "name": "Primary RDS Cluster",
                "type": "aws_rds_cluster",
                "provider": "aws",
                "region": "us-east-1",
                "is_redundant": True,
                "rto_minutes": 15,
                "rpo_minutes": 1,
                "status": "healthy",
            },
            # Replica database
            {
                "id": "db-002-replica",
                "name": "Replica RDS Cluster",
                "type": "aws_rds_cluster",
                "provider": "aws",
                "region": "us-west-2",
                "is_redundant": True,
                "rto_minutes": 15,
                "rpo_minutes": 5,
                "status": "healthy",
            },
            # API servers
            {
                "id": "api-001",
                "name": "API Server 1",
                "type": "aws_instance",
                "provider": "aws",
                "region": "us-east-1",
                "is_redundant": False,
                "rto_minutes": 5,
                "rpo_minutes": 0,
                "status": "healthy",
            },
            {
                "id": "api-002",
                "name": "API Server 2",
                "type": "aws_instance",
                "provider": "aws",
                "region": "us-east-1",
                "is_redundant": False,
                "rto_minutes": 5,
                "rpo_minutes": 0,
                "status": "healthy",
            },
            # Cache
            {
                "id": "cache-001",
                "name": "ElastiCache Redis",
                "type": "aws_elasticache",
                "provider": "aws",
                "region": "us-east-1",
                "is_redundant": True,
                "rto_minutes": 10,
                "rpo_minutes": 0,
                "status": "healthy",
            },
            # Load balancer
            {
                "id": "lb-001",
                "name": "ALB",
                "type": "aws_elb",
                "provider": "aws",
                "region": "us-east-1",
                "is_redundant": True,
                "rto_minutes": 2,
                "rpo_minutes": 0,
                "status": "healthy",
            },
            # Message queue
            {
                "id": "queue-001",
                "name": "SQS Queue",
                "type": "aws_sqs",
                "provider": "aws",
                "region": "us-east-1",
                "is_redundant": False,
                "rto_minutes": 30,
                "rpo_minutes": 5,
                "status": "healthy",
            },
            # S3 bucket
            {
                "id": "storage-001",
                "name": "S3 Bucket",
                "type": "aws_s3",
                "provider": "aws",
                "region": "us-east-1",
                "is_redundant": True,
                "rto_minutes": 60,
                "rpo_minutes": 0,
                "status": "healthy",
            },
            # Backup
            {
                "id": "backup-001",
                "name": "AWS Backup",
                "type": "aws_backup",
                "provider": "aws",
                "region": "us-west-2",
                "is_redundant": True,
                "rto_minutes": 120,
                "rpo_minutes": 60,
                "status": "healthy",
            },
        ]

        # Create nodes
        print("\n[INFO] Creating infrastructure nodes...")
        for node in nodes:
            await neo4j.merge_node(node)
        print(f"[OK] Created {len(nodes)} nodes")

        # Define dependencies and relationships
        # Note: Allowed relationship types: DEPENDS_ON, DEPLOYED_ON, DOCUMENTED_BY, INTERACTS_WITH, READS_FROM, STORES_IN, WRITES_TO
        edges = [
            # API servers depend on load balancer
            ("api-001", "lb-001", "DEPENDS_ON", {"latency_ms": 5}),
            ("api-002", "lb-001", "DEPENDS_ON", {"latency_ms": 5}),
            # API servers depend on database
            ("api-001", "db-001-primary", "DEPENDS_ON", {"latency_ms": 20}),
            ("api-002", "db-001-primary", "DEPENDS_ON", {"latency_ms": 20}),
            # API servers depend on cache
            ("api-001", "cache-001", "DEPENDS_ON", {"latency_ms": 10}),
            ("api-002", "cache-001", "DEPENDS_ON", {"latency_ms": 10}),
            # API servers depend on queue
            ("api-001", "queue-001", "DEPENDS_ON", {"latency_ms": 15}),
            ("api-002", "queue-001", "DEPENDS_ON", {"latency_ms": 15}),
            # Cache depends on database for warm-up
            ("cache-001", "db-001-primary", "DEPENDS_ON", {"latency_ms": 25}),
            # Queue depends on database for message processing
            ("queue-001", "db-001-primary", "DEPENDS_ON", {"latency_ms": 25}),
            # Replica database interacts with primary
            ("db-002-replica", "db-001-primary", "INTERACTS_WITH", {"latency_ms": 100}),
            # Backup stores data from primary
            ("backup-001", "db-001-primary", "STORES_IN", {"latency_ms": 50}),
            # API reads from storage
            ("api-001", "storage-001", "READS_FROM", {"latency_ms": 15}),
            ("api-002", "storage-001", "READS_FROM", {"latency_ms": 15}),
            # Queue writes to storage
            ("queue-001", "storage-001", "WRITES_TO", {"latency_ms": 20}),
        ]

        # Create edges
        print("[INFO] Creating relationships...")
        for source, target, rel_type, props in edges:
            await neo4j.merge_edge(source, target, rel_type, props)
        print(f"[OK] Created {len(edges)} relationships")

        # Run migration to add enhanced properties
        print("[INFO] Running migration to add recovery schema...")
        async with neo4j._driver.session() as session:
            await migrate_add_recovery_schema(session)

        # Verify
        topology = await neo4j.get_topology()
        print(f"\n[OK] Bootstrap complete!")
        print(f"    - Nodes: {len(topology['nodes'])}")
        print(f"    - Edges: {len(topology['edges'])}")

        return True

    except Exception as e:
        print(f"\n[ERROR] {e}\n")
        log.error("bootstrap_failed", error=str(e))
        return False
    finally:
        await neo4j.close()


if __name__ == "__main__":
    success = asyncio.run(bootstrap_infrastructure())
    sys.exit(0 if success else 1)
