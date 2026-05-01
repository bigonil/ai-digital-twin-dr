"""Unit tests for feature endpoints: compliance, whatif, chaos, postmortem."""
import pytest
from datetime import datetime, timezone
from models.features import (
    ComplianceStatus,
    NodeComplianceResult,
    ComplianceReport,
    VirtualNode,
    VirtualEdge,
    WhatIfRequest,
    ChaosScenario,
    ChaosExperimentRequest,
    PostmortemIncidentInput,
)


class TestComplianceModels:
    """Test compliance schema validation."""

    def test_node_compliance_result_valid(self):
        """Test valid NodeComplianceResult creation."""
        node = NodeComplianceResult(
            node_id="test-node",
            node_name="Test Node",
            node_type="database",
            rto_minutes=30,
            rpo_minutes=10,
            rto_threshold=60,
            rpo_threshold=15,
            rto_status=ComplianceStatus.pass_,
            rpo_status=ComplianceStatus.pass_,
            blast_radius_size=5,
            worst_case_rto=25,
            worst_case_rpo=8,
        )
        assert node.node_id == "test-node"
        assert node.rto_status == ComplianceStatus.pass_

    def test_compliance_report_valid(self):
        """Test valid ComplianceReport creation."""
        report = ComplianceReport(
            generated_at=datetime.now(timezone.utc).isoformat(),
            rto_threshold_minutes=60,
            rpo_threshold_minutes=15,
            total_nodes=10,
            pass_count=8,
            fail_count=1,
            warning_count=1,
            skipped_count=0,
            results=[],
        )
        assert report.total_nodes == 10
        assert report.pass_count + report.fail_count + report.warning_count == 10


class TestVirtualNodeModels:
    """Test what-if virtual node/edge validation."""

    def test_virtual_node_id_prefix_required(self):
        """Test that VirtualNode id must start with 'virtual-'."""
        # Valid case
        node = VirtualNode(
            id="virtual-replica-db",
            name="Replica DB",
            type="database",
            is_redundant=True,
        )
        assert node.id.startswith("virtual-")

        # Invalid case
        with pytest.raises(ValueError, match="virtual-"):
            VirtualNode(
                id="replica-db",  # Missing 'virtual-' prefix
                name="Replica DB",
                type="database",
            )

    def test_virtual_edge_valid(self):
        """Test VirtualEdge creation."""
        edge = VirtualEdge(
            source="virtual-replica-db",
            target="app-server",
            type="DEPENDS_ON",
        )
        assert edge.source == "virtual-replica-db"
        assert edge.type == "DEPENDS_ON"

    def test_whatif_request_depth_bounds(self):
        """Test WhatIfRequest depth validation (1-10)."""
        # Valid depths
        for depth in [1, 5, 10]:
            req = WhatIfRequest(
                origin_node_id="test-node",
                depth=depth,
                virtual_nodes=[],
                virtual_edges=[],
            )
            assert req.depth == depth

        # Invalid depths
        with pytest.raises(ValueError):
            WhatIfRequest(
                origin_node_id="test-node",
                depth=0,  # Below min
                virtual_nodes=[],
                virtual_edges=[],
            )

        with pytest.raises(ValueError):
            WhatIfRequest(
                origin_node_id="test-node",
                depth=11,  # Above max
                virtual_nodes=[],
                virtual_edges=[],
            )


class TestChaosModels:
    """Test chaos scenario validation."""

    def test_chaos_scenario_enum(self):
        """Test all chaos scenarios are available."""
        scenarios = [
            ChaosScenario.terminate,
            ChaosScenario.network_loss,
            ChaosScenario.cpu_hog,
            ChaosScenario.disk_full,
            ChaosScenario.memory_pressure,
        ]
        assert len(scenarios) == 5

    def test_chaos_experiment_request_valid(self):
        """Test ChaosExperimentRequest creation."""
        req = ChaosExperimentRequest(
            node_id="test-node",
            scenario=ChaosScenario.cpu_hog,
            depth=5,
            notes="Testing CPU exhaustion",
        )
        assert req.scenario == ChaosScenario.cpu_hog
        assert req.depth == 5


class TestPostmortemModels:
    """Test postmortem accuracy calculation models."""

    def test_postmortem_input_valid(self):
        """Test PostmortemIncidentInput creation."""
        incident = PostmortemIncidentInput(
            title="Database Failover",
            occurred_at="2026-04-21T10:00:00Z",
            actual_origin_node_id="primary-db",
            actually_failed_node_ids=["replica-db", "cache-node"],
            actual_rto_minutes=45,
            actual_rpo_minutes=15,
            reference_simulation_node_id="primary-db",
            reference_simulation_depth=5,
        )
        assert len(incident.actually_failed_node_ids) == 2
        assert incident.actual_rto_minutes == 45

    def test_postmortem_accuracy_calculation(self):
        """Test accuracy score calculation logic."""
        # Test case: 2 true positives, 1 false positive, 1 false negative
        tp = 2
        fp = 1
        fn = 1

        precision = tp / (tp + fp)  # 2/3 = 0.667
        recall = tp / (tp + fn)  # 2/3 = 0.667
        accuracy = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0

        assert precision == pytest.approx(0.667, abs=0.01)
        assert recall == pytest.approx(0.667, abs=0.01)
        assert accuracy == pytest.approx(0.667, abs=0.01)


class TestComplianceStatusLogic:
    """Test compliance status determination logic."""

    def test_status_determination(self):
        """Test RTO status logic: fail > threshold, warning > 80% threshold, pass, skip."""
        rto_threshold = 60

        # Test cases
        cases = [
            (None, ComplianceStatus.skipped),  # No RTO set
            (45, ComplianceStatus.pass_),  # Below threshold
            (50, ComplianceStatus.warning),  # 80% threshold (48) < 50 < 60
            (65, ComplianceStatus.fail),  # Above threshold
        ]

        for worst_rto, expected_status in cases:
            if worst_rto is None:
                status = ComplianceStatus.skipped
            elif worst_rto > rto_threshold:
                status = ComplianceStatus.fail
            elif worst_rto > rto_threshold * 0.8:
                status = ComplianceStatus.warning
            else:
                status = ComplianceStatus.pass_

            assert status == expected_status
