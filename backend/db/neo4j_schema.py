"""Neo4j schema definitions and type mappings for enhanced simulation"""

# InfraNode properties in Neo4j
INFRA_NODE_PROPERTIES = {
    # Existing
    "id": "string (unique)",
    "name": "string",
    "type": "string",
    "region": "string",
    "rto_minutes": "number",
    "rpo_minutes": "number",
    "status": "enum: healthy|degraded|failed|simulated_failure",
    "is_redundant": "boolean",
    # NEW: Recovery Strategy
    "recovery_strategy": "enum: replica_fallback|multi_az|stateless|backup_fallback|generic",
    "recovery_rules": "dict",
    # NEW: Monitoring State
    "monitoring_state": "enum: healthy|degraded|unknown",
    "last_monitoring_update": "timestamp",
    "observed_latency_ms": "number (optional)",
}

# Edge properties in Neo4j
EDGE_PROPERTIES = {
    # Existing
    "type": "string",
    # NEW: Latency Modeling
    "latency_ms": "number",
    "latency_type": "enum: static|variable",
    "jitter_ms": "number",
    # NEW: Contention Modeling
    "shares_resource": "boolean",
    "contention_factor": "number",
    # NEW: Circuit Breaker
    "has_circuit_breaker": "boolean",
    "breaker_threshold_seconds": "number",
    # NEW: Data Consistency
    "replication_lag_seconds": "number",
}

# Default latency per edge type (milliseconds)
LATENCY_DEFAULTS = {
    "REPLICATES_TO": 1000,
    "CALLS": 100,
    "ROUTES_TO": 50,
    "USES": 500,
    "SHARES_RESOURCE": 200,
    "TIMEOUT_CALLS": 1000,
    "DEPENDS_ON": 100,
}

# Mapping from resource type to recovery strategy
TYPE_TO_STRATEGY = {
    # AWS: Databases
    "aws_rds_cluster": "replica_fallback",
    "aws_rds_instance": "replica_fallback",
    "aws_aurora_cluster": "replica_fallback",
    "aws_db_instance": "replica_fallback",
    "aws_dynamodb_table": "multi_az",
    # AWS: Networking & Load Balancing
    "aws_elb": "multi_az",
    "aws_alb": "multi_az",
    "aws_lb": "multi_az",
    "aws_api_gateway": "stateless",
    # AWS: Compute
    "aws_lambda_function": "stateless",
    "aws_ecs_service": "stateless",
    "aws_ecs_task": "stateless",
    "aws_ecs_cluster": "stateless",
    "aws_ec2_instance": "generic",
    "aws_instance": "generic",
    "aws_autoscaling_group": "stateless",
    # AWS: Caching & Messaging
    "aws_elasticache_cluster": "replica_fallback",
    "aws_elasticache_replication_group": "replica_fallback",
    "aws_sqs_queue": "generic",
    "aws_sns_topic": "generic",
    # AWS: Storage
    "aws_s3_bucket": "stateless",
    "aws_ebs_volume": "backup_fallback",
    "aws_backup_vault": "stateless",
    # AWS: CDN
    "aws_cloudfront_distribution": "stateless",

    # Azure: Databases
    "azurerm_mssql_server": "replica_fallback",
    "azurerm_mssql_database": "replica_fallback",
    "azurerm_mysql_flexible_server": "backup_fallback",
    "azurerm_mysql_server": "backup_fallback",
    "azurerm_postgresql_flexible_server": "backup_fallback",
    "azurerm_postgresql_server": "backup_fallback",
    "azurerm_cosmosdb_account": "multi_az",
    "azurerm_mariadb_server": "backup_fallback",
    # Azure: Networking & Load Balancing
    "azurerm_application_gateway": "multi_az",
    "azurerm_load_balancer": "multi_az",
    "azurerm_traffic_manager_profile": "stateless",
    "azurerm_virtual_network": "stateless",
    "azurerm_subnet": "stateless",
    "azurerm_network_security_group": "stateless",
    # Azure: Compute
    "azurerm_virtual_machine": "generic",
    "azurerm_virtual_machine_scale_set": "stateless",
    "azurerm_container_instance": "stateless",
    "azurerm_app_service": "stateless",
    "azurerm_app_service_plan": "stateless",
    "azurerm_kubernetes_cluster": "stateless",
    # Azure: Caching
    "azurerm_redis_cache": "replica_fallback",
    # Azure: Storage
    "azurerm_storage_account": "stateless",
    "azurerm_storage_blob": "stateless",
    # Azure: CDN
    "azurerm_cdn_endpoint": "stateless",

    # GCP: Databases
    "google_sql_database_instance": "replica_fallback",
    "google_sql_database": "replica_fallback",
    "google_bigtable_instance": "multi_az",
    "google_firestore_database": "multi_az",
    "google_spanner_instance": "multi_az",
    # GCP: Networking & Load Balancing
    "google_compute_backend_service": "multi_az",
    "google_compute_health_check": "stateless",
    "google_compute_load_balancer": "multi_az",
    "google_compute_network": "stateless",
    "google_compute_subnetwork": "stateless",
    "google_compute_firewall": "stateless",
    # GCP: Compute
    "google_compute_instance": "generic",
    "google_compute_instance_group": "stateless",
    "google_compute_instance_group_manager": "stateless",
    "google_compute_instance_template": "stateless",
    "google_container_cluster": "stateless",
    "google_container_node_pool": "stateless",
    "google_cloud_run_service": "stateless",
    # GCP: Caching
    "google_redis_instance": "replica_fallback",
    "google_memcache_instance": "replica_fallback",
    # GCP: Storage
    "google_storage_bucket": "stateless",
    # GCP: CDN
    "google_compute_backend_service": "multi_az",
}

# Inference rules for edge type based on source and target resource types
LATENCY_INFERENCE_RULES = {
    "rds_to_rds": "REPLICATES_TO",
    "lambda_to_rds": "CALLS",
    "lambda_to_lambda": "CALLS",
    "instance_to_rds": "CALLS",
    "instance_to_lambda": "CALLS",
    "instance_to_instance": "CALLS",
    "ecs_to_rds": "CALLS",
    "alb_to_instance": "ROUTES_TO",
    "alb_to_ecs": "ROUTES_TO",
    "elb_to_instance": "ROUTES_TO",
}


async def ensure_node_properties(neo4j_session, node_id: str, defaults: dict) -> None:
    """
    Ensure all properties exist on an InfraNode, setting defaults if missing.

    Args:
        neo4j_session: Neo4j session
        node_id: Node ID
        defaults: Dict of default values {property: value} - property names must be valid InfraNode properties
    """
    # Validate that all property names are known/safe
    valid_properties = set(INFRA_NODE_PROPERTIES.keys())
    for key in defaults.keys():
        if key not in valid_properties:
            raise ValueError(f"Invalid property '{key}' for InfraNode. Valid properties: {valid_properties}")

    properties_set = []
    for key, value in defaults.items():
        if value is not None:
            properties_set.append(f"SET n.{key} = ${key}")

    if not properties_set:
        return

    query = f"MATCH (n:InfraNode {{id: $node_id}}) {' '.join(properties_set)}"
    await neo4j_session.run(query, {"node_id": node_id, **defaults})


async def ensure_edge_properties(neo4j_session, edge_type: str, defaults: dict) -> None:
    """
    Ensure all edges of a type have required properties, setting defaults if missing.

    Args:
        neo4j_session: Neo4j session
        edge_type: Type of relationship - must be a valid edge type (REPLICATES_TO, CALLS, etc.)
        defaults: Dict of default values {property: value} - property names must be valid edge properties
    """
    # Validate that edge_type is known/safe
    valid_edge_types = set(LATENCY_DEFAULTS.keys())
    if edge_type not in valid_edge_types:
        raise ValueError(f"Invalid edge type '{edge_type}'. Valid types: {valid_edge_types}")

    # Validate that all property names are known/safe
    valid_properties = set(EDGE_PROPERTIES.keys())
    for key in defaults.keys():
        if key not in valid_properties:
            raise ValueError(f"Invalid property '{key}' for edges. Valid properties: {valid_properties}")

    properties_set = []
    for key, value in defaults.items():
        if value is not None:
            properties_set.append(f"SET r.{key} = ${key}")

    if not properties_set:
        return

    query = f"MATCH ()-[r]->() WHERE type(r) = $edge_type {' '.join(properties_set)}"
    await neo4j_session.run(query, {"edge_type": edge_type, **defaults})
