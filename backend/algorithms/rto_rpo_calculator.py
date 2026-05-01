"""Dynamic RTO/RPO calculation based on recovery strategy and dependency health"""

from typing import Dict, Any, List, Set, Tuple


def calculate_effective_rto(
    node: Dict[str, Any],
    replicas: List[Dict[str, Any]],
    affected_node_ids: Set[str],
) -> float:
    """
    Calculate effective RTO based on recovery strategy.

    Args:
        node: Node dict with recovery_strategy, rto_minutes, recovery_rules
        replicas: List of replica nodes with rto_minutes
        affected_node_ids: Set of nodes already affected in blast radius

    Returns:
        Effective RTO in minutes
    """
    recovery_strategy = node.get("recovery_strategy", "generic")
    node_rto = node.get("rto_minutes", 60)

    if recovery_strategy == "replica_fallback":
        # Check if replicas are healthy
        healthy_replicas = [r for r in replicas if r["id"] not in affected_node_ids]

        if healthy_replicas:
            # Use minimum replica RTO
            return min(r.get("rto_minutes", node_rto) for r in healthy_replicas)
        elif replicas:
            # Replicas exist but all are degraded
            return node_rto * 1.5
        else:
            # No replicas, use fallback multiplier
            fallback_mult = node.get("recovery_rules", {}).get("fallback_rto_multiplier", 2.0)
            return node_rto * fallback_mult

    elif recovery_strategy == "multi_az":
        # Multi-AZ failover is fast
        return node_rto * 0.5

    elif recovery_strategy == "stateless":
        # Stateless nodes can be spun up quickly
        return node_rto * 0.5

    elif recovery_strategy == "backup_fallback":
        # Similar to replica_fallback but for backups
        fallback_mult = node.get("recovery_rules", {}).get("fallback_rto_multiplier", 2.0)
        return node_rto * fallback_mult

    else:
        # Generic: use static RTO
        return node_rto


def calculate_effective_rpo(
    node: Dict[str, Any],
    replication_lag_seconds: int = 0,
) -> float:
    """
    Calculate effective RPO based on replication lag.

    Args:
        node: Node dict with rpo_minutes
        replication_lag_seconds: Replication lag in seconds

    Returns:
        Effective RPO in minutes
    """
    node_rpo = node.get("rpo_minutes", 0)
    lag_minutes = replication_lag_seconds / 60.0
    return node_rpo + lag_minutes


def apply_monitoring_state_impact(
    node: Dict[str, Any],
    effective_rto: float,
) -> Tuple[float, bool]:
    """
    Apply monitoring state impact to RTO and at_risk flag.

    Args:
        node: Node dict with monitoring_state
        effective_rto: Effective RTO before monitoring adjustment

    Returns:
        Tuple of (adjusted_effective_rto, at_risk)
    """
    monitoring_state = node.get("monitoring_state", "unknown")

    if monitoring_state == "degraded":
        # Already compromised, recovery will be slower
        return effective_rto * 1.5, True
    elif monitoring_state == "healthy":
        return effective_rto, False
    else:
        # unknown: no impact
        return effective_rto, False
