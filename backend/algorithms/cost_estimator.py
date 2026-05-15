"""
Cost estimation for infrastructure nodes and recovery strategies.
Provides per-hour and recovery cost estimates based on node type + region.
"""

from typing import Optional

# Hourly cost (USD) per resource type — P50 estimates for us-east-1
# Values based on publicly available AWS on-demand pricing
_BASE_HOURLY_COST_USD: dict[str, float] = {
    "aws_db_instance": 0.17,       # db.t3.medium RDS
    "aws_rds_cluster": 0.29,       # db.r6g.large Aurora
    "aws_lb": 0.008,               # ALB + LCU
    "aws_instance": 0.046,         # t3.medium EC2
    "aws_s3_bucket": 0.023,        # per GB/month → approx per hour (100GB bucket)
    "aws_sqs_queue": 0.0004,       # per 1M requests → approx per hour
    "aws_elasticache_cluster": 0.068,  # cache.t3.medium
    "aws_eks_cluster": 0.10,       # cluster fee + managed nodegroup
    "aws_lambda_function": 0.0002, # per-invocation — approx
    "aws_cloudfront": 0.0085,      # per GB transfer
    "generic": 0.05,
}

# Regional cost multiplier (relative to us-east-1 = 1.0)
_REGION_MULTIPLIER: dict[str, float] = {
    "us-east-1": 1.0,
    "us-east-2": 1.0,
    "us-west-1": 1.10,
    "us-west-2": 1.03,
    "eu-west-1": 1.15,
    "eu-west-2": 1.18,
    "eu-central-1": 1.20,
    "ap-southeast-1": 1.25,
    "ap-northeast-1": 1.30,
    "ap-south-1": 1.15,
    "sa-east-1": 1.40,
}

# Recovery cost multiplier based on strategy
# Reflects extra compute/ops cost during the recovery window
_STRATEGY_RECOVERY_MULTIPLIER: dict[str, float] = {
    "replica_fallback": 1.5,    # promote replica, brief downtime, minimal extra cost
    "multi_az": 1.2,            # automatic failover, near-zero extra cost
    "stateless": 1.1,           # spin up replacement, cheap
    "backup_fallback": 4.0,     # slow restore, temporary extra instances
    "generic": 2.5,
}


def estimate_hourly_cost(node_type: str, region: Optional[str] = None) -> float:
    """Estimate hourly cost in USD for a node given type and region."""
    base = _BASE_HOURLY_COST_USD.get(node_type, _BASE_HOURLY_COST_USD["generic"])
    multiplier = _REGION_MULTIPLIER.get(region or "us-east-1", 1.0)
    return round(base * multiplier, 4)


def estimate_recovery_cost(
    node_type: str,
    region: Optional[str],
    recovery_strategy: Optional[str],
    rto_minutes: Optional[int],
) -> float:
    """
    Estimate total cost (USD) of a recovery event.

    Formula:
        recovery_cost = hourly_cost × (rto_minutes / 60) × strategy_multiplier + base_ops_cost
    """
    hourly = estimate_hourly_cost(node_type, region)
    rto_hours = (rto_minutes or 60) / 60
    strategy = recovery_strategy or "generic"
    multiplier = _STRATEGY_RECOVERY_MULTIPLIER.get(strategy, 2.5)
    ops_cost = 50.0  # flat ops/engineer cost per incident (USD)

    return round(hourly * rto_hours * multiplier + ops_cost, 2)


def annotate_nodes_with_cost(
    affected_nodes: list[dict],
    strategy_override: Optional[str] = None,
) -> list[dict]:
    """
    Add cost fields to each affected node dict.
    Returns new list with cost fields added (non-destructive).
    """
    annotated = []
    for node in affected_nodes:
        node_type = node.get("type", "generic")
        region = node.get("region")
        strategy = strategy_override or node.get("recovery_strategy", "generic")
        rto = node.get("rto_minutes") or node.get("estimated_rto_minutes") or node.get("effective_rto_minutes")

        annotated.append({
            **node,
            "hourly_cost_usd": estimate_hourly_cost(node_type, region),
            "recovery_cost_usd": estimate_recovery_cost(node_type, region, strategy, rto),
        })
    return annotated
