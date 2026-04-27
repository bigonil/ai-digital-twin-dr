import pytest
from models.enhanced_graph import (
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

from db.neo4j_schema import (
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


from parsers.strategy_inference import (
    infer_recovery_strategy,
    infer_edge_type,
    infer_recovery_rules,
    get_default_latency,
)


def test_infer_recovery_strategy():
    """Verify recovery strategy inference from resource type"""
    assert infer_recovery_strategy("aws_rds_cluster") == "replica_fallback"
    assert infer_recovery_strategy("aws_rds_instance") == "replica_fallback"
    assert infer_recovery_strategy("aws_alb") == "multi_az"
    assert infer_recovery_strategy("aws_lambda_function") == "stateless"
    assert infer_recovery_strategy("aws_ec2_instance") == "generic"
    assert infer_recovery_strategy("unknown_type") == "generic"  # Default


def test_infer_edge_type():
    """Verify edge type inference from source and target types"""
    # RDS to RDS = REPLICATES_TO
    assert infer_edge_type("aws_rds_cluster", "aws_rds_cluster") == "REPLICATES_TO"

    # Lambda/Instance to RDS = CALLS
    assert infer_edge_type("aws_lambda_function", "aws_rds_cluster") == "CALLS"
    assert infer_edge_type("aws_instance", "aws_rds_cluster") == "CALLS"

    # ALB to Instance = ROUTES_TO
    assert infer_edge_type("aws_alb", "aws_instance") == "ROUTES_TO"

    # Default = DEPENDS_ON
    assert infer_edge_type("aws_s3_bucket", "aws_lambda_function") == "DEPENDS_ON"


def test_infer_recovery_rules():
    """Verify recovery rules inference"""
    # replica_fallback with replicas
    rules = infer_recovery_rules("replica_fallback", has_replica=True, has_backup=False)
    assert rules["fallback_rto_multiplier"] == 2.0

    # replica_fallback without replicas
    rules = infer_recovery_rules("replica_fallback", has_replica=False, has_backup=False)
    assert rules["fallback_rto_multiplier"] == 3.0

    # multi_az
    rules = infer_recovery_rules("multi_az", has_replica=False, has_backup=False)
    assert "fallback_rto_multiplier" in rules or rules == {}


def test_get_default_latency():
    """Verify latency defaults per edge type"""
    assert get_default_latency("REPLICATES_TO") == 1000
    assert get_default_latency("CALLS") == 100
    assert get_default_latency("ROUTES_TO") == 50
    assert get_default_latency("DEPENDS_ON") == 100
    assert get_default_latency("UNKNOWN_TYPE") == 100  # Default


from algorithms.cascading_failure import bfs_with_latency


def test_bfs_latency_accumulation():
    """
    Verify BFS accumulates latency per hop, not linear.

    Scenario: A → B (CALLS: 100ms) → C (REPLICATES_TO: 1000ms)
    Expected step_time_ms: A=0, B=100, C=1100
    """
    # Mock graph structure
    nodes = {
        "A": {"id": "A", "name": "Node A"},
        "B": {"id": "B", "name": "Node B"},
        "C": {"id": "C", "name": "Node C"},
    }
    edges = {
        "A": [{"target": "B", "latency_ms": 100, "shares_resource": False, "contention_factor": 1.0}],
        "B": [{"target": "C", "latency_ms": 1000, "shares_resource": False, "contention_factor": 1.0}],
        "C": [],
    }

    def get_outgoing_edges_fn(node_id):
        return edges.get(node_id, [])

    def get_node_details_fn(node_id):
        return nodes.get(node_id)

    affected = bfs_with_latency("A", depth=5,
                                 get_outgoing_edges_fn=get_outgoing_edges_fn,
                                 get_node_details_fn=get_node_details_fn)

    assert affected["A"]["step_time_ms"] == 0
    assert affected["B"]["step_time_ms"] == 100
    assert affected["C"]["step_time_ms"] == 1100


def test_bfs_contention_factor():
    """
    Verify contention factor multiplies latency when resource already affected.

    Scenario: A → B (latency=100, no contention)
            A → C (latency=100, shares_resource=True, contention_factor=1.5)

    If B is already affected and C shares resource:
    Expected: C.step_time_ms = 100 × 1.5 = 150
    """
    nodes = {
        "A": {"id": "A", "name": "Node A"},
        "B": {"id": "B", "name": "Node B"},
        "C": {"id": "C", "name": "Node C"},
    }
    edges = {
        "A": [
            {"target": "B", "latency_ms": 100, "shares_resource": False, "contention_factor": 1.0},
            {"target": "C", "latency_ms": 100, "shares_resource": True, "contention_factor": 1.5},
        ],
        "B": [],
        "C": [],
    }

    def get_outgoing_edges_fn(node_id):
        return edges.get(node_id, [])

    def get_node_details_fn(node_id):
        return nodes.get(node_id)

    affected = bfs_with_latency("A", depth=5,
                                 get_outgoing_edges_fn=get_outgoing_edges_fn,
                                 get_node_details_fn=get_node_details_fn)

    # B is affected, so C's contention factor applies: 100 × 1.5 = 150
    assert affected["C"]["step_time_ms"] == 150


def test_bfs_depth_limit():
    """Verify BFS respects depth limit"""
    nodes = {
        "A": {"id": "A", "name": "Node A"},
        "B": {"id": "B", "name": "Node B"},
        "C": {"id": "C", "name": "Node C"},
    }
    edges = {
        "A": [{"target": "B", "latency_ms": 100, "shares_resource": False, "contention_factor": 1.0}],
        "B": [{"target": "C", "latency_ms": 100, "shares_resource": False, "contention_factor": 1.0}],
        "C": [],
    }

    def get_outgoing_edges_fn(node_id):
        return edges.get(node_id, [])

    def get_node_details_fn(node_id):
        return nodes.get(node_id)

    # depth=1: only A and B
    affected = bfs_with_latency("A", depth=1,
                                 get_outgoing_edges_fn=get_outgoing_edges_fn,
                                 get_node_details_fn=get_node_details_fn)

    assert "A" in affected
    assert "B" in affected
    assert "C" not in affected


from algorithms.rto_rpo_calculator import (
    calculate_effective_rto,
    calculate_effective_rpo,
    apply_monitoring_state_impact,
)

def test_rto_replica_fallback_healthy_replica():
    """
    replica_fallback with healthy replica: use replica's RTO.
    """
    node = {
        "id": "primary",
        "rto_minutes": 15,
        "recovery_strategy": "replica_fallback",
        "recovery_rules": {"fallback_rto_multiplier": 2.0},
    }
    replicas = [
        {"id": "replica_1", "rto_minutes": 5},
        {"id": "replica_2", "rto_minutes": 7},
    ]
    affected_node_ids = set()  # No affected nodes

    effective_rto = calculate_effective_rto(node, replicas, affected_node_ids)
    assert effective_rto == 5  # min(replica RTOs)

def test_rto_replica_fallback_degraded_replicas():
    """
    replica_fallback with degraded replicas: use node.rto × 1.5.
    """
    node = {
        "id": "primary",
        "rto_minutes": 15,
        "recovery_strategy": "replica_fallback",
        "recovery_rules": {"fallback_rto_multiplier": 2.0},
    }
    replicas = [
        {"id": "replica_1", "rto_minutes": 5},
    ]
    affected_node_ids = {"replica_1"}  # Replica is affected

    effective_rto = calculate_effective_rto(node, replicas, affected_node_ids)
    assert effective_rto == 15 * 1.5  # 22.5

def test_rto_replica_fallback_no_replica():
    """
    replica_fallback without replicas: use node.rto × fallback_rto_multiplier.
    """
    node = {
        "id": "primary",
        "rto_minutes": 15,
        "recovery_strategy": "replica_fallback",
        "recovery_rules": {"fallback_rto_multiplier": 3.0},
    }
    replicas = []
    affected_node_ids = set()

    effective_rto = calculate_effective_rto(node, replicas, affected_node_ids)
    assert effective_rto == 15 * 3.0  # 45

def test_rto_multi_az():
    """
    multi_az: fast failover, use node.rto × 0.5.
    """
    node = {
        "id": "lb",
        "rto_minutes": 10,
        "recovery_strategy": "multi_az",
    }
    replicas = []
    affected_node_ids = set()

    effective_rto = calculate_effective_rto(node, replicas, affected_node_ids)
    assert effective_rto == 10 * 0.5  # 5

def test_rto_stateless():
    """
    stateless: quick spinup, use node.rto × 0.5.
    """
    node = {
        "id": "lambda",
        "rto_minutes": 2,
        "recovery_strategy": "stateless",
    }
    replicas = []
    affected_node_ids = set()

    effective_rto = calculate_effective_rto(node, replicas, affected_node_ids)
    assert effective_rto == 2 * 0.5  # 1

def test_rto_generic():
    """
    generic: use static RTO.
    """
    node = {
        "id": "instance",
        "rto_minutes": 20,
        "recovery_strategy": "generic",
    }
    replicas = []
    affected_node_ids = set()

    effective_rto = calculate_effective_rto(node, replicas, affected_node_ids)
    assert effective_rto == 20  # Static

def test_rpo_with_replication_lag():
    """
    RPO affected by replication lag: effective_rpo = node.rpo + (lag_seconds / 60).
    """
    node = {
        "id": "primary",
        "rpo_minutes": 1,
    }
    replication_lag_seconds = 30

    effective_rpo = calculate_effective_rpo(node, replication_lag_seconds)
    assert effective_rpo == 1 + (30 / 60)  # 1.5

def test_monitoring_state_degraded():
    """
    degraded monitoring state: multiply RTO by 1.5 and set at_risk=True.
    """
    node = {
        "id": "instance",
        "rto_minutes": 10,
        "monitoring_state": "degraded",
    }

    effective_rto, at_risk = apply_monitoring_state_impact(node, 10)
    assert effective_rto == 10 * 1.5  # 15
    assert at_risk is True

def test_monitoring_state_healthy():
    """
    healthy monitoring state: no impact.
    """
    node = {
        "id": "instance",
        "rto_minutes": 10,
        "monitoring_state": "healthy",
    }

    effective_rto, at_risk = apply_monitoring_state_impact(node, 10)
    assert effective_rto == 10
    assert at_risk is False


from parsers.infra import parse_directory, _infer_strategies, _infer_edges, _set_default_latencies, _infer_all_recovery_rules
import tempfile
import os

def test_parser_phase1_extract_resources(tmp_path):
    """
    Phase 1: Extract resources from Terraform files.
    """
    # Create sample Terraform file
    tf_content = """
resource "aws_rds_cluster" "primary" {
  cluster_identifier = "my-database"
  engine = "aurora-postgresql"
}

resource "aws_instance" "app" {
  instance_type = "t3.micro"
  ami = "ami-12345"
}
"""
    tf_file = tmp_path / "main.tf"
    tf_file.write_text(tf_content)

    # Parse using the refactored parser
    nodes, edges = parse_directory(str(tmp_path))

    # Should extract at least the resource types
    assert isinstance(nodes, list)
    assert len(nodes) >= 2

    # Verify resource types are present
    node_types = {node.type for node in nodes}
    assert "aws_rds_cluster" in node_types
    assert "aws_instance" in node_types


def test_parser_phase2_infer_strategies():
    """Phase 2: Infer recovery strategies from resource types"""
    resources = [
        {"id": "aws_rds_cluster.primary", "type": "aws_rds_cluster", "name": "primary", "config": {}},
        {"id": "aws_lambda_function.api", "type": "aws_lambda_function", "name": "api", "config": {}},
        {"id": "aws_alb.frontend", "type": "aws_alb", "name": "frontend", "config": {}},
    ]

    result = _infer_strategies(resources)

    # Find each resource in result
    rds = next(r for r in result if r["id"] == "aws_rds_cluster.primary")
    lambda_fn = next(r for r in result if r["id"] == "aws_lambda_function.api")
    alb = next(r for r in result if r["id"] == "aws_alb.frontend")

    assert rds.get("recovery_strategy") == "replica_fallback"
    assert lambda_fn.get("recovery_strategy") == "stateless"
    assert alb.get("recovery_strategy") == "multi_az"


def test_parser_phase3_infer_edges():
    """Phase 3: Infer edge types from resource relationships"""
    resources = [
        {"id": "aws_rds_cluster.primary", "type": "aws_rds_cluster", "name": "primary", "references": ["aws_rds_cluster.replica"]},
        {"id": "aws_rds_cluster.replica", "type": "aws_rds_cluster", "name": "replica", "references": []},
        {"id": "aws_instance.app", "type": "aws_instance", "name": "app", "references": ["aws_rds_cluster.primary"]},
    ]

    edges = _infer_edges(resources)

    assert any(e["source"] == "aws_rds_cluster.primary" and e["target"] == "aws_rds_cluster.replica" and e["type"] == "REPLICATES_TO" for e in edges)
    assert any(e["source"] == "aws_instance.app" and e["target"] == "aws_rds_cluster.primary" and e["type"] == "CALLS" for e in edges)


def test_parser_phase4_set_latencies():
    """Phase 4: Set default latencies per edge type"""
    edges = [
        {"source": "a", "target": "b", "type": "REPLICATES_TO"},
        {"source": "b", "target": "c", "type": "CALLS"},
    ]

    result = _set_default_latencies(edges)

    replicates_edge = next(e for e in result if e["type"] == "REPLICATES_TO")
    calls_edge = next(e for e in result if e["type"] == "CALLS")

    assert replicates_edge.get("latency_ms") == 1000
    assert calls_edge.get("latency_ms") == 100


def test_parser_phase5_infer_recovery_rules():
    """Phase 5: Infer recovery rules"""
    resources = [
        {"id": "primary", "type": "aws_rds_cluster", "recovery_strategy": "replica_fallback"},
    ]
    edges = [
        {"source": "primary", "target": "replica", "type": "REPLICATES_TO"},
    ]

    result = _infer_all_recovery_rules(resources, edges)

    primary = next(r for r in result if r["id"] == "primary")
    rules = primary.get("recovery_rules", {})

    assert rules.get("replica_edge") == "REPLICATES_TO"
    assert rules.get("fallback_rto_multiplier") == 2.0  # has replica


def test_neo4j_client_import():
    """Verify Neo4j client can be imported"""
    from db import neo4j_client
    assert neo4j_client is not None
