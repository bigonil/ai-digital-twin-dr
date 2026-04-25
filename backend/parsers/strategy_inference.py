"""Inference functions for recovery strategy, edge types, and recovery rules"""

from backend.db.neo4j_schema import (
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

    Args:
        source_type: Source resource type
        target_type: Target resource type

    Returns:
        Edge type (e.g., "REPLICATES_TO", "CALLS", "ROUTES_TO")
    """
    # RDS to RDS = REPLICATES_TO
    if source_type.startswith("aws_rds") and target_type.startswith("aws_rds"):
        return "REPLICATES_TO"

    # Lambda/Instance/ECS to RDS = CALLS
    if any(source_type.startswith(t) for t in ["aws_lambda", "aws_instance", "aws_ecs"]):
        if target_type.startswith("aws_rds"):
            return "CALLS"

    # ALB/ELB to Instance/ECS = ROUTES_TO
    if any(source_type.startswith(t) for t in ["aws_alb", "aws_lb", "aws_elb"]):
        if any(target_type.startswith(t) for t in ["aws_instance", "aws_ecs"]):
            return "ROUTES_TO"

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
