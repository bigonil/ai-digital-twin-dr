"""Inference functions for recovery strategy, edge types, and recovery rules"""

from db.neo4j_schema import (
    TYPE_TO_STRATEGY,
    LATENCY_DEFAULTS,
    LATENCY_INFERENCE_RULES,
)


def infer_recovery_strategy(resource_type: str) -> str:
    """
    Infer recovery strategy from resource type.

    Args:
        resource_type: AWS resource type (e.g., "aws_rds_cluster")

    Returns:
        Recovery strategy string (e.g., "replica_fallback")
    """
    return TYPE_TO_STRATEGY.get(resource_type, "generic")


def infer_edge_type(source_type: str, target_type: str) -> str:
    """
    Infer edge type from source and target resource types.
    Supports AWS, Azure, and GCP resource patterns.

    Args:
        source_type: Source resource type (e.g., "aws_rds_cluster", "azurerm_mssql_server", "google_sql_database_instance")
        target_type: Target resource type

    Returns:
        Edge type (e.g., "REPLICATES_TO", "CALLS", "ROUTES_TO")
    """
    # ============================================
    # Database-to-Database Replication
    # ============================================
    # AWS RDS to RDS
    if source_type.startswith("aws_rds") and target_type.startswith("aws_rds"):
        return "REPLICATES_TO"
    if source_type.startswith("aws_aurora") and target_type.startswith("aws_aurora"):
        return "REPLICATES_TO"

    # Azure SQL to SQL
    if source_type.startswith("azurerm_mssql") and target_type.startswith("azurerm_mssql"):
        return "REPLICATES_TO"

    # Azure MySQL to MySQL
    if (source_type.startswith("azurerm_mysql") and target_type.startswith("azurerm_mysql")):
        return "REPLICATES_TO"

    # Azure PostgreSQL to PostgreSQL
    if (source_type.startswith("azurerm_postgresql") and target_type.startswith("azurerm_postgresql")):
        return "REPLICATES_TO"

    # Azure CosmosDB to CosmosDB (multi-region replication)
    if source_type.startswith("azurerm_cosmosdb") and target_type.startswith("azurerm_cosmosdb"):
        return "REPLICATES_TO"

    # Azure Redis to Redis
    if source_type.startswith("azurerm_redis") and target_type.startswith("azurerm_redis"):
        return "REPLICATES_TO"

    # GCP Cloud SQL to Cloud SQL
    if source_type.startswith("google_sql") and target_type.startswith("google_sql"):
        return "REPLICATES_TO"

    # GCP Bigtable to Bigtable
    if source_type.startswith("google_bigtable") and target_type.startswith("google_bigtable"):
        return "REPLICATES_TO"

    # GCP Firestore to Firestore
    if source_type.startswith("google_firestore") and target_type.startswith("google_firestore"):
        return "REPLICATES_TO"

    # GCP Spanner to Spanner
    if source_type.startswith("google_spanner") and target_type.startswith("google_spanner"):
        return "REPLICATES_TO"

    # GCP Redis to Redis
    if source_type.startswith("google_redis") and target_type.startswith("google_redis"):
        return "REPLICATES_TO"

    # GCP Memcache to Memcache
    if source_type.startswith("google_memcache") and target_type.startswith("google_memcache"):
        return "REPLICATES_TO"

    # ============================================
    # Compute-to-Database Calls
    # ============================================
    # AWS Compute (Lambda, Instance, ECS) to AWS Database
    aws_compute = ["aws_lambda", "aws_instance", "aws_ec2", "aws_ecs"]
    aws_db = ["aws_rds", "aws_aurora", "aws_dynamodb"]
    if any(source_type.startswith(t) for t in aws_compute):
        if any(target_type.startswith(t) for t in aws_db):
            return "CALLS"

    # Azure Compute to Azure Database
    azure_compute = ["azurerm_virtual_machine", "azurerm_container_instance", "azurerm_app_service", "azurerm_kubernetes_cluster"]
    azure_db = ["azurerm_mssql", "azurerm_mysql", "azurerm_postgresql", "azurerm_cosmosdb"]
    if any(source_type.startswith(t) for t in azure_compute):
        if any(target_type.startswith(t) for t in azure_db):
            return "CALLS"

    # GCP Compute to GCP Database
    gcp_compute = ["google_compute_instance", "google_container_cluster", "google_cloud_run_service", "google_app_engine"]
    gcp_db = ["google_sql", "google_bigtable", "google_firestore", "google_spanner"]
    if any(source_type.startswith(t) for t in gcp_compute):
        if any(target_type.startswith(t) for t in gcp_db):
            return "CALLS"

    # ============================================
    # Load Balancer Routing
    # ============================================
    # AWS Load Balancers to Compute
    aws_lb = ["aws_alb", "aws_lb", "aws_elb", "aws_api_gateway"]
    aws_compute_targets = ["aws_instance", "aws_ecs", "aws_lambda"]
    if any(source_type.startswith(t) for t in aws_lb):
        if any(target_type.startswith(t) for t in aws_compute_targets):
            return "ROUTES_TO"

    # Azure Load Balancers to Compute
    azure_lb = ["azurerm_application_gateway", "azurerm_load_balancer", "azurerm_traffic_manager"]
    azure_compute_targets = ["azurerm_virtual_machine", "azurerm_app_service", "azurerm_container_instance", "azurerm_kubernetes_cluster"]
    if any(source_type.startswith(t) for t in azure_lb):
        if any(target_type.startswith(t) for t in azure_compute_targets):
            return "ROUTES_TO"

    # GCP Load Balancers to Compute
    gcp_lb = ["google_compute_backend_service", "google_compute_load_balancer"]
    gcp_compute_targets = ["google_compute_instance_group", "google_cloud_run_service", "google_container_cluster"]
    if any(source_type.startswith(t) for t in gcp_lb):
        if any(target_type.startswith(t) for t in gcp_compute_targets):
            return "ROUTES_TO"

    # ============================================
    # Cache/Messaging Dependencies
    # ============================================
    # Compute to Cache
    if any(source_type.startswith(t) for t in aws_compute + azure_compute + gcp_compute):
        if any(target_type.startswith(t) for t in ["elasticache", "redis", "memcache"]):
            return "USES"

    # Compute to Message Queue/Topic
    if any(source_type.startswith(t) for t in aws_compute + azure_compute + gcp_compute):
        if any(target_type.startswith(t) for t in ["sqs", "sns", "servicebus", "pubsub"]):
            return "USES"

    # Default = DEPENDS_ON
    return "DEPENDS_ON"


def infer_recovery_rules(
    recovery_strategy: str,
    has_replica: bool = False,
    has_backup: bool = False
) -> dict:
    """
    Infer recovery rules based on strategy and dependencies.

    Args:
        recovery_strategy: Recovery strategy
        has_replica: Whether node has replicas
        has_backup: Whether node has backups

    Returns:
        Dict of recovery rules
    """
    if recovery_strategy == "replica_fallback":
        return {
            "replica_edge": "REPLICATES_TO",
            "backup_edge": "BACKED_UP_BY",
            "fallback_rto_multiplier": 2.0 if has_replica else 3.0,
        }
    elif recovery_strategy == "multi_az":
        return {
            "fallback_rto_multiplier": 0.5,
        }
    elif recovery_strategy == "stateless":
        return {
            "fallback_rto_multiplier": 0.5,
        }
    else:
        return {}


def get_default_latency(edge_type: str) -> int:
    """
    Get default latency for edge type.

    Args:
        edge_type: Edge type (e.g., "REPLICATES_TO")

    Returns:
        Latency in milliseconds
    """
    return LATENCY_DEFAULTS.get(edge_type, 100)
