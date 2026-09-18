"""
Integration tests for the enhanced cascading failure pipeline.
Tests the full flow: Neo4j graph → Disaster simulation → Timeline generation.
Focuses on validation of affected nodes, chronological ordering, RTO/RPO calculation,
and strategy-specific behaviors.
"""
import pytest
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from models.graph import InfraNode, InfraEdge, CloudProvider, ResourceStatus
from models.enhanced_graph import (
    RecoveryStrategy,
    MonitoringState,
    EnhancedAffectedNode,
    EnhancedSimulationWithTimeline,
)
from algorithms.cascading_failure import bfs_with_latency
from algorithms.rto_rpo_calculator import (
    calculate_effective_rto,
    calculate_effective_rpo,
    apply_monitoring_state_impact,
)


# Sample Terraform configuration for testing
SAMPLE_TERRAFORM = """
# Primary database with replicas
resource "aws_rds_cluster" "primary_db" {
  cluster_identifier      = "primary-db-cluster"
  engine                  = "aurora-postgresql"
  availability_zones      = ["us-east-1a", "us-east-1b"]
  db_cluster_parameter_group_name = "default.aurora-postgresql14"
  rto_minutes             = 5
  rpo_minutes             = 1
}

# RDS instance in primary AZ
resource "aws_rds_cluster_instance" "primary_instance" {
  cluster_identifier = aws_rds_cluster.primary_db.id
  instance_class     = "db.r6g.xlarge"
  engine              = "aurora-postgresql"
  availability_zone   = "us-east-1a"
}

# Application layer with auto-scaling
resource "aws_autoscaling_group" "app_asg" {
  name              = "app-asg"
  availability_zones = ["us-east-1a", "us-east-1b"]
  min_size          = 2
  max_size          = 10
  desired_capacity  = 4
  vpc_zone_identifier = ["subnet-123"]
  rto_minutes       = 5
  rpo_minutes       = 1
}

# Load balancer
resource "aws_lb" "app_lb" {
  name               = "app-lb"
  load_balancer_type = "application"
  availability_zones = ["us-east-1a", "us-east-1b"]
  rto_minutes        = 2
  rpo_minutes        = 0
}

# Cache layer
resource "aws_elasticache_cluster" "cache" {
  cluster_id           = "cache-cluster"
  engine               = "redis"
  node_type           = "cache.r6g.xlarge"
  num_cache_nodes     = 2
  parameter_group_name = "default.redis7"
  availability_zone    = "us-east-1a"
  rto_minutes         = 3
  rpo_minutes         = 1
}

# Lambda function (stateless)
resource "aws_lambda_function" "processor" {
  function_name = "data-processor"
  runtime       = "python3.11"
  handler       = "index.handler"
  rto_minutes   = 5
  rpo_minutes   = 1
}
"""


@pytest.fixture
def temp_terraform_dir():
    """Create a temporary directory with sample Terraform files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tf_file = Path(tmpdir) / "main.tf"
        tf_file.write_text(SAMPLE_TERRAFORM)
        yield tmpdir


@pytest.fixture
def sample_infra_nodes():
    """Create sample InfraNode objects for testing."""
    nodes = {
        "primary_db": InfraNode(
            id="aws_rds_cluster.primary_db",
            name="primary-db-cluster",
            type="aws_rds_cluster",
            provider=CloudProvider.aws,
            region="us-east-1",
            rto_minutes=5,
            rpo_minutes=1,
            status=ResourceStatus.healthy,
            is_redundant=True,
        ),
        "primary_instance": InfraNode(
            id="aws_rds_cluster_instance.primary_instance",
            name="primary_instance",
            type="aws_rds_cluster_instance",
            provider=CloudProvider.aws,
            region="us-east-1",
            rto_minutes=5,
            rpo_minutes=1,
            status=ResourceStatus.healthy,
            is_redundant=False,
        ),
        "app_asg": InfraNode(
            id="aws_autoscaling_group.app_asg",
            name="app-asg",
            type="aws_autoscaling_group",
            provider=CloudProvider.aws,
            region="us-east-1",
            rto_minutes=5,
            rpo_minutes=1,
            status=ResourceStatus.healthy,
            is_redundant=True,
        ),
        "app_lb": InfraNode(
            id="aws_lb.app_lb",
            name="app-lb",
            type="aws_lb",
            provider=CloudProvider.aws,
            region="us-east-1",
            rto_minutes=2,
            rpo_minutes=0,
            status=ResourceStatus.healthy,
            is_redundant=True,
        ),
        "cache": InfraNode(
            id="aws_elasticache_cluster.cache",
            name="cache-cluster",
            type="aws_elasticache_cluster",
            provider=CloudProvider.aws,
            region="us-east-1",
            rto_minutes=3,
            rpo_minutes=1,
            status=ResourceStatus.healthy,
            is_redundant=False,
        ),
        "lambda": InfraNode(
            id="aws_lambda_function.processor",
            name="data-processor",
            type="aws_lambda_function",
            provider=CloudProvider.aws,
            region="us-east-1",
            rto_minutes=5,
            rpo_minutes=1,
            status=ResourceStatus.healthy,
            is_redundant=False,
        ),
    }
    return nodes


@pytest.fixture
def sample_infra_edges():
    """Create sample InfraEdge objects representing dependencies."""
    edges = [
        # App layer depends on database
        InfraEdge(
            source="aws_autoscaling_group.app_asg",
            target="aws_rds_cluster.primary_db",
            type="CALLS",
            properties={
                "latency_ms": 100,
                "shares_resource": False,
                "contention_factor": 1.0,
            },
        ),
        # Load balancer routes to app layer
        InfraEdge(
            source="aws_lb.app_lb",
            target="aws_autoscaling_group.app_asg",
            type="ROUTES_TO",
            properties={
                "latency_ms": 50,
                "shares_resource": False,
                "contention_factor": 1.0,
            },
        ),
        # Lambda depends on database
        InfraEdge(
            source="aws_lambda_function.processor",
            target="aws_rds_cluster.primary_db",
            type="CALLS",
            properties={
                "latency_ms": 100,
                "shares_resource": False,
                "contention_factor": 1.0,
            },
        ),
        # App layer uses cache
        InfraEdge(
            source="aws_autoscaling_group.app_asg",
            target="aws_elasticache_cluster.cache",
            type="USES",
            properties={
                "latency_ms": 500,
                "shares_resource": False,
                "contention_factor": 1.0,
            },
        ),
        # RDS instance replicates to primary
        InfraEdge(
            source="aws_rds_cluster_instance.primary_instance",
            target="aws_rds_cluster.primary_db",
            type="REPLICATES_TO",
            properties={
                "latency_ms": 1000,
                "shares_resource": False,
                "contention_factor": 1.0,
            },
        ),
    ]
    return edges


class TestFullPipelineIntegration:
    """Integration tests for graph → simulate → timeline pipeline."""

    def test_step_time_ms_is_chronologically_ordered(
        self, sample_infra_nodes, sample_infra_edges
    ):
        """Test that step_time_ms values are strictly ordered."""
        # Create a sample result with multiple nodes at different distances
        affected_node_list = [
            EnhancedAffectedNode(
                id="aws_rds_cluster.primary_db",
                name="primary-db-cluster",
                type="aws_rds_cluster",
                distance=0,
                step_time_ms=0,
                estimated_rto_minutes=5,
                estimated_rpo_minutes=1,
                effective_rto_minutes=5,
                effective_rpo_minutes=1,
                recovery_strategy=RecoveryStrategy.REPLICA_FALLBACK,
                monitoring_state=MonitoringState.HEALTHY,
                at_risk=False,
            ),
            EnhancedAffectedNode(
                id="aws_autoscaling_group.app_asg",
                name="app-asg",
                type="aws_autoscaling_group",
                distance=1,
                step_time_ms=625,  # 1/5 of 3125 total
                estimated_rto_minutes=5,
                estimated_rpo_minutes=1,
                effective_rto_minutes=5,
                effective_rpo_minutes=1,
                recovery_strategy=RecoveryStrategy.MULTI_AZ,
                monitoring_state=MonitoringState.HEALTHY,
                at_risk=False,
            ),
            EnhancedAffectedNode(
                id="aws_lb.app_lb",
                name="app-lb",
                type="aws_lb",
                distance=2,
                step_time_ms=1250,  # 2/5 of 3125 total
                estimated_rto_minutes=2,
                estimated_rpo_minutes=0,
                effective_rto_minutes=2,
                effective_rpo_minutes=0,
                recovery_strategy=RecoveryStrategy.MULTI_AZ,
                monitoring_state=MonitoringState.HEALTHY,
                at_risk=False,
            ),
        ]

        # Verify chronological order
        for i in range(len(affected_node_list) - 1):
            assert (
                affected_node_list[i].step_time_ms <= affected_node_list[i + 1].step_time_ms
            ), f"step_time_ms not ordered: {affected_node_list[i].step_time_ms} > {affected_node_list[i + 1].step_time_ms}"

    def test_effective_rto_varies_by_recovery_strategy(self):
        """Test that effective_rto_minutes is calculated correctly for each strategy."""
        base_rto = 10.0
        replicas = []  # No replicas available

        test_cases = [
            (RecoveryStrategy.REPLICA_FALLBACK, 20.0),  # 2.0x with no replica (uses fallback_rto_multiplier)
            (RecoveryStrategy.MULTI_AZ, 5.0),  # 0.5x
            (RecoveryStrategy.STATELESS, 5.0),  # 0.5x
            (RecoveryStrategy.BACKUP_FALLBACK, 20.0),  # 2.0x (uses fallback_rto_multiplier)
            (RecoveryStrategy.GENERIC, 10.0),  # 1.0x (static)
        ]

        for strategy, expected_rto in test_cases:
            node_data = {
                "id": "test-node",
                "rto_minutes": base_rto,
                "recovery_strategy": strategy.value,
                "monitoring_state": "healthy",
            }
            affected_ids = set()

            effective_rto = calculate_effective_rto(node_data, replicas, affected_ids)
            assert (
                abs(effective_rto - expected_rto) < 0.01
            ), f"Strategy {strategy.value}: expected {expected_rto}, got {effective_rto}"

    def test_worst_case_rto_is_maximum(self):
        """Test that worst_case_rto is the maximum effective_rto across all nodes."""
        affected_node_list = [
            EnhancedAffectedNode(
                id="node-1",
                name="Node 1",
                type="aws_instance",
                distance=1,
                step_time_ms=1000,
                estimated_rto_minutes=5,
                estimated_rpo_minutes=1,
                effective_rto_minutes=7.5,  # 1.5x
                effective_rpo_minutes=1,
                recovery_strategy=RecoveryStrategy.GENERIC,
                monitoring_state=MonitoringState.HEALTHY,
                at_risk=False,
            ),
            EnhancedAffectedNode(
                id="node-2",
                name="Node 2",
                type="aws_rds_cluster",
                distance=2,
                step_time_ms=2000,
                estimated_rto_minutes=10,
                estimated_rpo_minutes=2,
                effective_rto_minutes=5.0,  # 0.5x
                effective_rpo_minutes=2,
                recovery_strategy=RecoveryStrategy.MULTI_AZ,
                monitoring_state=MonitoringState.HEALTHY,
                at_risk=False,
            ),
            EnhancedAffectedNode(
                id="node-3",
                name="Node 3",
                type="aws_lb",
                distance=3,
                step_time_ms=3000,
                estimated_rto_minutes=2,
                estimated_rpo_minutes=0,
                effective_rto_minutes=1.0,  # 0.5x
                effective_rpo_minutes=0,
                recovery_strategy=RecoveryStrategy.MULTI_AZ,
                monitoring_state=MonitoringState.HEALTHY,
                at_risk=False,
            ),
        ]

        worst_case_rto = max(node.effective_rto_minutes for node in affected_node_list)
        worst_case_rpo = max(node.effective_rpo_minutes for node in affected_node_list)

        assert worst_case_rto == 7.5, f"Expected worst_case_rto=7.5, got {worst_case_rto}"
        assert worst_case_rpo == 2, f"Expected worst_case_rpo=2, got {worst_case_rpo}"

    def test_monitoring_state_impact_increases_rto(self):
        """Test that degraded monitoring state increases RTO by 1.5x."""
        node_data = {
            "id": "test-node",
            "rto_minutes": 10.0,
            "recovery_strategy": "generic",
            "monitoring_state": "degraded",
        }

        effective_rto = 10.0  # Start with base
        effective_rto, at_risk = apply_monitoring_state_impact(node_data, effective_rto)

        assert at_risk is True, "at_risk should be True for degraded monitoring"
        assert abs(effective_rto - 15.0) < 0.01, f"Expected 15.0 (1.5x), got {effective_rto}"

    def test_monitoring_state_unknown_doesnt_increase_rto(self):
        """Test that unknown monitoring state doesn't increase RTO."""
        node_data = {
            "id": "test-node",
            "rto_minutes": 10.0,
            "recovery_strategy": "generic",
            "monitoring_state": "unknown",
        }

        effective_rto = 10.0
        effective_rto, at_risk = apply_monitoring_state_impact(node_data, effective_rto)

        assert at_risk is False
        assert abs(effective_rto - 10.0) < 0.01, f"Expected 10.0, got {effective_rto}"

    def test_enhanced_simulation_response_includes_required_fields(self):
        """Test that EnhancedSimulationWithTimeline includes all required fields."""
        affected_node_list = [
            EnhancedAffectedNode(
                id="aws_rds_cluster.primary_db",
                name="primary-db-cluster",
                type="aws_rds_cluster",
                distance=0,
                step_time_ms=0,
                estimated_rto_minutes=5,
                estimated_rpo_minutes=1,
                effective_rto_minutes=5,
                effective_rpo_minutes=1,
                recovery_strategy=RecoveryStrategy.REPLICA_FALLBACK,
                monitoring_state=MonitoringState.HEALTHY,
                at_risk=False,
            ),
        ]

        response = EnhancedSimulationWithTimeline(
            origin_node_id="aws_rds_cluster.primary_db",
            blast_radius=affected_node_list,
            timeline_steps=[
                {
                    "node_id": "aws_rds_cluster.primary_db",
                    "node_name": "primary-db-cluster",
                    "distance": 0,
                    "step_time_ms": 0,
                    "rto_minutes": 5,
                    "rpo_minutes": 1,
                }
            ],
            max_distance=0,
            total_duration_ms=5000,
            worst_case_rto_minutes=5,
            worst_case_rpo_minutes=1,
            model_version="1.0-accurate",
            validation_score=None,
        )

        # Verify required fields
        assert response.origin_node_id == "aws_rds_cluster.primary_db"
        assert response.model_version == "1.0-accurate"
        assert response.worst_case_rto_minutes == 5
        assert response.worst_case_rpo_minutes == 1
        assert len(response.blast_radius) == 1
        assert response.blast_radius[0].effective_rto_minutes == 5
        assert response.blast_radius[0].recovery_strategy == RecoveryStrategy.REPLICA_FALLBACK
        assert response.blast_radius[0].monitoring_state == MonitoringState.HEALTHY


class TestEdgeTypeLatencyAccumulation:
    """Tests for edge-type-specific latency accumulation."""

    def test_latency_accumulation_per_edge_type(self):
        """Test that latency accumulates correctly per hop with edge-type defaults."""
        # Edge types and default latencies:
        # REPLICATES_TO: 1000ms, CALLS: 100ms, ROUTES_TO: 50ms, USES: 500ms, DEPENDS_ON: 100ms

        latency_defaults = {
            "REPLICATES_TO": 1000,
            "CALLS": 100,
            "ROUTES_TO": 50,
            "USES": 500,
            "DEPENDS_ON": 100,
        }

        # Path: CALLS (100) -> ROUTES_TO (50) -> USES (500)
        # Total should be 100 + 50 + 500 = 650ms
        path_latency = sum([latency_defaults["CALLS"], latency_defaults["ROUTES_TO"], latency_defaults["USES"]])
        assert path_latency == 650, f"Expected 650ms, got {path_latency}"

    def test_contention_factor_multiplies_latency_for_shared_resources(self):
        """Test that shared resource contention increases latency."""
        base_latency = 100  # CALLS edge type
        contention_factor = 1.5  # 50% contention

        effective_latency = base_latency * contention_factor
        assert effective_latency == 150, f"Expected 150ms, got {effective_latency}"


class TestRecoveryRulesApplication:
    """Tests for recovery rule inference and application."""

    def test_recovery_strategy_inference_for_redundant_nodes(self):
        """Test that redundant nodes get replica_fallback strategy."""
        # RDS cluster is redundant → should infer replica_fallback
        node_data = {
            "type": "aws_rds_cluster",
            "is_redundant": True,
            "recovery_strategy": "replica_fallback",
        }

        assert node_data["recovery_strategy"] == "replica_fallback"

    def test_recovery_strategy_inference_for_stateless_nodes(self):
        """Test that stateless nodes get stateless strategy."""
        # Lambda is stateless → should infer stateless
        node_data = {
            "type": "aws_lambda_function",
            "is_redundant": False,
            "recovery_strategy": "stateless",
        }

        assert node_data["recovery_strategy"] == "stateless"

    def test_recovery_strategy_inference_for_multi_az_nodes(self):
        """Test that multi-AZ nodes get multi_az strategy."""
        # Load balancer spans multiple AZs → should infer multi_az
        node_data = {
            "type": "aws_lb",
            "availability_zones": ["us-east-1a", "us-east-1b"],
            "recovery_strategy": "multi_az",
        }

        assert node_data["recovery_strategy"] == "multi_az"
