"""
Migration script to add recovery strategy and monitoring state properties to existing InfraNodes.
Run once on existing databases before deploying enhanced simulation.
"""

from db.neo4j_schema import TYPE_TO_STRATEGY, LATENCY_DEFAULTS


async def migrate_add_recovery_schema(neo4j_session):
    """
    Migrate existing InfraNodes to include new properties:
    - recovery_strategy (inferred from type)
    - recovery_rules (empty dict by default)
    - monitoring_state (default: "unknown")
    - observed_latency_ms (null)
    - last_monitoring_update (null)

    Args:
        neo4j_session: Neo4j session
    """
    print("Starting migration: add_recovery_schema...")

    # Step 1: Set recovery_strategy based on resource type
    print("  Setting recovery_strategy...")
    for resource_type, strategy in TYPE_TO_STRATEGY.items():
        query = """
        MATCH (n:InfraNode {type: $type})
        SET n.recovery_strategy = $strategy
        RETURN count(n) as updated_count
        """
        result = await neo4j_session.run(query, {"type": resource_type, "strategy": strategy})
        record = await result.single()
        if record:
            print(f"    {resource_type} → {strategy}: {record['updated_count']} nodes")

    # Step 2: Set monitoring_state to "unknown" for all nodes without it
    print("  Setting monitoring_state...")
    query = """
    MATCH (n:InfraNode)
    WHERE n.monitoring_state IS NULL
    SET n.monitoring_state = "unknown"
    RETURN count(n) as updated_count
    """
    result = await neo4j_session.run(query)
    record = await result.single()
    if record:
        print(f"    Set monitoring_state for {record['updated_count']} nodes")

    # Step 3: Set default latencies on edges
    print("  Setting default latencies on edges...")
    for edge_type, latency_ms in LATENCY_DEFAULTS.items():
        query = """
        MATCH ()-[r]->()
        WHERE type(r) = $edge_type AND r.latency_ms IS NULL
        SET r.latency_ms = $latency_ms, r.latency_type = "static"
        RETURN count(r) as updated_count
        """
        result = await neo4j_session.run(query, {"edge_type": edge_type, "latency_ms": latency_ms})
        record = await result.single()
        if record:
            print(f"    {edge_type}: {record['updated_count']} edges")

    # Step 4: Set recovery_rules to empty dict for nodes without it
    print("  Setting recovery_rules...")
    query = """
    MATCH (n:InfraNode)
    WHERE n.recovery_rules IS NULL
    SET n.recovery_rules = {}
    RETURN count(n) as updated_count
    """
    result = await neo4j_session.run(query)
    record = await result.single()
    if record:
        print(f"    Set recovery_rules for {record['updated_count']} nodes")

    print("Migration complete!")


# Note: This migration is called from application startup, not meant to be run directly.
# To run manually, use: python -m db.neo4j_client and call migrate_add_recovery_schema(session)
