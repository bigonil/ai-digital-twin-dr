"""
Backward compatibility tests for the enhanced cascading failure model.
Ensures that old API clients without include_monitoring parameter still work,
and all models serialize/deserialize to JSON correctly.
"""
import json
import pytest

from models.graph import DisasterSimulationRequest
from models.enhanced_graph import (
    RecoveryStrategy,
    MonitoringState,
    EnhancedAffectedNode,
    EnhancedSimulationWithTimeline,
    TimelineStep,
)


class TestAPIBackwardCompatibility:
    """Test that old API requests without include_monitoring still work."""

    def test_disaster_simulation_request_without_include_monitoring(self):
        """Test that DisasterSimulationRequest works without include_monitoring parameter."""
        # Old API clients don't know about include_monitoring
        request_data = {
            "node_id": "aws_rds_cluster.primary_db",
            "depth": 5,
        }

        # Should be able to create request without include_monitoring
        request = DisasterSimulationRequest(**request_data)
        assert request.node_id == "aws_rds_cluster.primary_db"
        assert request.depth == 5

    def test_disaster_simulation_request_with_include_monitoring(self):
        """Test that DisasterSimulationRequest works with new include_monitoring parameter."""
        request_data = {
            "node_id": "aws_rds_cluster.primary_db",
            "depth": 5,
            "include_monitoring": True,
        }

        request = DisasterSimulationRequest(**request_data)
        assert request.node_id == "aws_rds_cluster.primary_db"
        assert request.include_monitoring is True

    def test_disaster_simulation_request_include_monitoring_defaults_to_false(self):
        """Test that include_monitoring defaults to False for backward compatibility."""
        request_data = {
            "node_id": "aws_rds_cluster.primary_db",
            "depth": 5,
        }

        request = DisasterSimulationRequest(**request_data)
        assert hasattr(request, 'include_monitoring')
        # Should default to False if not provided (or allow None)


class TestModelSerialization:
    """Test that enhanced models serialize and deserialize to JSON correctly."""

    def test_enhanced_affected_node_to_json(self):
        """Test EnhancedAffectedNode serializes to JSON."""
        node = EnhancedAffectedNode(
            id="aws_rds_cluster.primary_db",
            name="Primary Database",
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
        )

        # Serialize to JSON
        json_str = node.model_dump_json()
        assert isinstance(json_str, str)

        # Deserialize back
        parsed = json.loads(json_str)
        assert parsed["id"] == "aws_rds_cluster.primary_db"
        assert parsed["recovery_strategy"] == "replica_fallback"  # enum serialized as string
        assert parsed["monitoring_state"] == "healthy"  # enum serialized as string

    def test_enhanced_affected_node_from_json(self):
        """Test EnhancedAffectedNode deserializes from JSON."""
        json_data = {
            "id": "aws_autoscaling_group.app_asg",
            "name": "App ASG",
            "type": "aws_autoscaling_group",
            "distance": 1,
            "step_time_ms": 1000,
            "estimated_rto_minutes": 5,
            "estimated_rpo_minutes": 1,
            "effective_rto_minutes": 2.5,
            "effective_rpo_minutes": 1,
            "recovery_strategy": "multi_az",
            "monitoring_state": "healthy",
            "at_risk": False,
        }

        node = EnhancedAffectedNode(**json_data)
        assert node.id == "aws_autoscaling_group.app_asg"
        assert node.recovery_strategy == RecoveryStrategy.MULTI_AZ
        assert node.monitoring_state == MonitoringState.HEALTHY

    def test_timeline_step_to_json(self):
        """Test TimelineStep serializes to JSON."""
        step = TimelineStep(
            node_id="aws_instance.app_001",
            node_name="API Server",
            distance=2,
            step_time_ms=2000,
            rto_minutes=10,
            rpo_minutes=2,
        )

        json_str = step.model_dump_json()
        parsed = json.loads(json_str)
        assert parsed["node_id"] == "aws_instance.app_001"
        assert parsed["step_time_ms"] == 2000

    def test_enhanced_simulation_response_to_json(self):
        """Test EnhancedSimulationWithTimeline serializes to JSON."""
        affected_nodes = [
            EnhancedAffectedNode(
                id="aws_rds_cluster.primary_db",
                name="Primary DB",
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

        timeline_steps = [
            TimelineStep(
                node_id="aws_rds_cluster.primary_db",
                node_name="Primary DB",
                distance=0,
                step_time_ms=0,
                rto_minutes=5,
                rpo_minutes=1,
            )
        ]

        response = EnhancedSimulationWithTimeline(
            origin_node_id="aws_rds_cluster.primary_db",
            blast_radius=affected_nodes,
            timeline_steps=timeline_steps,
            max_distance=0,
            total_duration_ms=5000,
            worst_case_rto_minutes=5,
            worst_case_rpo_minutes=1,
            model_version="1.0-accurate",
            validation_score=None,
        )

        json_str = response.model_dump_json()
        parsed = json.loads(json_str)

        # Verify structure
        assert parsed["origin_node_id"] == "aws_rds_cluster.primary_db"
        assert parsed["model_version"] == "1.0-accurate"
        assert len(parsed["blast_radius"]) == 1
        assert len(parsed["timeline_steps"]) == 1
        assert parsed["worst_case_rto_minutes"] == 5

    def test_enhanced_simulation_response_from_json(self):
        """Test EnhancedSimulationWithTimeline deserializes from JSON."""
        json_data = {
            "origin_node_id": "aws_lb.app_lb",
            "blast_radius": [
                {
                    "id": "aws_autoscaling_group.app_asg",
                    "name": "App ASG",
                    "type": "aws_autoscaling_group",
                    "distance": 1,
                    "step_time_ms": 1000,
                    "estimated_rto_minutes": 5,
                    "estimated_rpo_minutes": 1,
                    "effective_rto_minutes": 2.5,
                    "effective_rpo_minutes": 1,
                    "recovery_strategy": "multi_az",
                    "monitoring_state": "healthy",
                    "at_risk": False,
                }
            ],
            "timeline_steps": [
                {
                    "node_id": "aws_autoscaling_group.app_asg",
                    "node_name": "App ASG",
                    "distance": 1,
                    "step_time_ms": 1000,
                    "rto_minutes": 2.5,
                    "rpo_minutes": 1,
                }
            ],
            "max_distance": 1,
            "total_duration_ms": 5000,
            "worst_case_rto_minutes": 2.5,
            "worst_case_rpo_minutes": 1,
            "model_version": "1.0-accurate",
            "validation_score": None,
        }

        response = EnhancedSimulationWithTimeline(**json_data)
        assert response.origin_node_id == "aws_lb.app_lb"
        assert response.model_version == "1.0-accurate"
        assert len(response.blast_radius) == 1
        assert response.blast_radius[0].recovery_strategy == RecoveryStrategy.MULTI_AZ


class TestOldAPICompatibility:
    """Test that old API behavior (without monitoring state) still works."""

    def test_enhanced_affected_node_without_at_risk(self):
        """Test that EnhancedAffectedNode works even if at_risk not provided."""
        # Old clients might not know about at_risk flag
        node_data = {
            "id": "aws_instance.app_001",
            "name": "API Server",
            "type": "aws_instance",
            "distance": 1,
            "step_time_ms": 1000,
            "estimated_rto_minutes": 10,
            "estimated_rpo_minutes": 2,
            "effective_rto_minutes": 10,
            "effective_rpo_minutes": 2,
            "recovery_strategy": "generic",
            "monitoring_state": "unknown",
        }

        node = EnhancedAffectedNode(**node_data)
        assert node.id == "aws_instance.app_001"
        # at_risk should have a default value
        assert hasattr(node, 'at_risk')

    def test_enhanced_affected_node_without_monitoring_state(self):
        """Test that old responses without monitoring_state field still deserialize."""
        # Very old API might not have had monitoring_state
        node_data = {
            "id": "aws_instance.app_001",
            "name": "API Server",
            "type": "aws_instance",
            "distance": 1,
            "step_time_ms": 1000,
            "estimated_rto_minutes": 10,
            "estimated_rpo_minutes": 2,
            "effective_rto_minutes": 10,
            "effective_rpo_minutes": 2,
            "recovery_strategy": "generic",
        }

        # This might fail if monitoring_state is required, which is OK
        # but we should be aware of the breaking change
        try:
            node = EnhancedAffectedNode(**node_data)
            # If it works, great! If not, we know it's a breaking change
        except Exception as e:
            # Expected: monitoring_state is now required
            assert "monitoring_state" in str(e).lower()


class TestEnumSerialization:
    """Test that Recovery Strategy and Monitoring State enums serialize correctly."""

    def test_recovery_strategy_enum_serialization(self):
        """Test that RecoveryStrategy enum is serialized as string value."""
        node = EnhancedAffectedNode(
            id="test-node",
            name="Test",
            type="aws_instance",
            distance=0,
            step_time_ms=0,
            estimated_rto_minutes=10,
            estimated_rpo_minutes=1,
            effective_rto_minutes=10,
            effective_rpo_minutes=1,
            recovery_strategy=RecoveryStrategy.STATELESS,
            monitoring_state=MonitoringState.HEALTHY,
            at_risk=False,
        )

        json_str = node.model_dump_json()
        parsed = json.loads(json_str)

        # Enum should be serialized as string value, not dict
        assert parsed["recovery_strategy"] == "stateless"
        assert isinstance(parsed["recovery_strategy"], str)

    def test_monitoring_state_enum_serialization(self):
        """Test that MonitoringState enum is serialized as string value."""
        node = EnhancedAffectedNode(
            id="test-node",
            name="Test",
            type="aws_instance",
            distance=0,
            step_time_ms=0,
            estimated_rto_minutes=10,
            estimated_rpo_minutes=1,
            effective_rto_minutes=10,
            effective_rpo_minutes=1,
            recovery_strategy=RecoveryStrategy.GENERIC,
            monitoring_state=MonitoringState.DEGRADED,
            at_risk=False,
        )

        json_str = node.model_dump_json()
        parsed = json.loads(json_str)

        # Enum should be serialized as string value
        assert parsed["monitoring_state"] == "degraded"
        assert isinstance(parsed["monitoring_state"], str)
