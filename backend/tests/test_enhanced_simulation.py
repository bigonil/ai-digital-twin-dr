import pytest
from backend.models.enhanced_graph import (
    RecoveryStrategy,
    MonitoringState,
    RecoveryRules,
    EnhancedInfraNode,
    EnhancedAffectedNode,
    EnhancedSimulationWithTimeline,
)

def test_recovery_strategy_enum():
    """Verify RecoveryStrategy enum has all required values"""
    assert RecoveryStrategy.REPLICA_FALLBACK.value == "replica_fallback"
    assert RecoveryStrategy.MULTI_AZ.value == "multi_az"
    assert RecoveryStrategy.STATELESS.value == "stateless"
    assert RecoveryStrategy.BACKUP_FALLBACK.value == "backup_fallback"
    assert RecoveryStrategy.GENERIC.value == "generic"
    assert len(RecoveryStrategy) == 5

def test_monitoring_state_enum():
    """Verify MonitoringState enum has all required values"""
    assert MonitoringState.HEALTHY.value == "healthy"
    assert MonitoringState.DEGRADED.value == "degraded"
    assert MonitoringState.UNKNOWN.value == "unknown"
    assert len(MonitoringState) == 3

def test_recovery_rules_model():
    """Verify RecoveryRules model can be instantiated"""
    rules = RecoveryRules(
        replica_edge="REPLICATES_TO",
        backup_edge="BACKED_UP_BY",
        fallback_rto_multiplier=2.0,
        circuit_breaker_threshold_seconds=30,
    )
    assert rules.replica_edge == "REPLICATES_TO"
    assert rules.fallback_rto_multiplier == 2.0

def test_enhanced_infra_node_model():
    """Verify EnhancedInfraNode has recovery_strategy and monitoring_state"""
    rules = RecoveryRules(replica_edge="REPLICATES_TO", fallback_rto_multiplier=2.0)
    node = EnhancedInfraNode(
        id="aws_rds_cluster.primary",
        name="Primary DB",
        type="aws_rds_cluster",
        rto_minutes=15,
        rpo_minutes=1,
        recovery_strategy=RecoveryStrategy.REPLICA_FALLBACK,
        recovery_rules=rules,
        monitoring_state=MonitoringState.HEALTHY,
        observed_latency_ms=None,
    )
    assert node.recovery_strategy == RecoveryStrategy.REPLICA_FALLBACK
    assert node.monitoring_state == MonitoringState.HEALTHY

def test_enhanced_affected_node_model():
    """Verify EnhancedAffectedNode includes effective_rto_minutes and at_risk"""
    affected = EnhancedAffectedNode(
        id="aws_instance.app_001",
        name="API Server",
        type="aws_instance",
        distance=1,
        step_time_ms=100,
        estimated_rto_minutes=10,
        estimated_rpo_minutes=2,
        effective_rto_minutes=15,
        effective_rpo_minutes=2,
        recovery_strategy=RecoveryStrategy.STATELESS,
        monitoring_state=MonitoringState.DEGRADED,
        at_risk=True,
    )
    assert affected.effective_rto_minutes == 15
    assert affected.at_risk is True

def test_enhanced_simulation_response_model():
    """Verify EnhancedSimulationWithTimeline includes model_version"""
    response = EnhancedSimulationWithTimeline(
        origin_node_id="aws_rds_cluster.primary",
        blast_radius=[],
        timeline_steps=[],
        max_distance=0,
        total_duration_ms=5000,
        worst_case_rto_minutes=15,
        worst_case_rpo_minutes=1,
        model_version="1.0-accurate",
        validation_score=None,
    )
    assert response.model_version == "1.0-accurate"

from backend.db.neo4j_schema import (
    INFRA_NODE_PROPERTIES,
    EDGE_PROPERTIES,
    LATENCY_DEFAULTS,
    TYPE_TO_STRATEGY,
    LATENCY_INFERENCE_RULES,
)

def test_infra_node_properties_dict():
    """Verify INFRA_NODE_PROPERTIES has all required fields"""
    required_fields = [
        "id", "name", "type", "rto_minutes", "rpo_minutes",
        "recovery_strategy", "recovery_rules", "monitoring_state",
        "observed_latency_ms", "last_monitoring_update", "status",
        "region", "is_redundant"
    ]
    for field in required_fields:
        assert field in INFRA_NODE_PROPERTIES, f"Missing {field} in INFRA_NODE_PROPERTIES"

def test_edge_properties_dict():
    """Verify EDGE_PROPERTIES has all required fields"""
    required_fields = [
        "type", "latency_ms", "latency_type", "jitter_ms",
        "shares_resource", "contention_factor", "has_circuit_breaker",
        "breaker_threshold_seconds", "replication_lag_seconds"
    ]
    for field in required_fields:
        assert field in EDGE_PROPERTIES, f"Missing {field} in EDGE_PROPERTIES"

def test_latency_defaults_dict():
    """Verify LATENCY_DEFAULTS has all edge types"""
    expected_types = ["REPLICATES_TO", "CALLS", "ROUTES_TO", "USES", "DEPENDS_ON", "SHARES_RESOURCE", "TIMEOUT_CALLS"]
    for edge_type in expected_types:
        assert edge_type in LATENCY_DEFAULTS, f"Missing {edge_type} in LATENCY_DEFAULTS"

    assert LATENCY_DEFAULTS["REPLICATES_TO"] == 1000
    assert LATENCY_DEFAULTS["CALLS"] == 100
    assert LATENCY_DEFAULTS["ROUTES_TO"] == 50

def test_type_to_strategy_mapping():
    """Verify TYPE_TO_STRATEGY maps resource types to recovery strategies"""
    assert TYPE_TO_STRATEGY["aws_rds_cluster"] == "replica_fallback"
    assert TYPE_TO_STRATEGY["aws_rds_instance"] == "replica_fallback"
    assert TYPE_TO_STRATEGY["aws_alb"] == "multi_az"
    assert TYPE_TO_STRATEGY["aws_lambda_function"] == "stateless"
    assert "aws_ec2_instance" in TYPE_TO_STRATEGY
    assert "aws_s3_bucket" in TYPE_TO_STRATEGY

def test_latency_inference_rules():
    """Verify LATENCY_INFERENCE_RULES provides inference logic"""
    assert "rds_to_rds" in LATENCY_INFERENCE_RULES
    assert LATENCY_INFERENCE_RULES["rds_to_rds"] == "REPLICATES_TO"
    assert "lambda_to_rds" in LATENCY_INFERENCE_RULES
    assert LATENCY_INFERENCE_RULES["lambda_to_rds"] == "CALLS"
