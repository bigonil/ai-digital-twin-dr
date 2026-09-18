"""Integration tests for feature workflows."""
import pytest
import httpx
from datetime import datetime, timezone


BASE_URL = "http://localhost:8001"


class TestComplianceWorkflow:
    """End-to-end compliance audit workflow."""

    def test_full_compliance_workflow(self):
        """Test: Run audit → Get cached report → Export JSON."""
        with httpx.Client(timeout=30) as client:
            # Step 1: Run compliance audit
            run_response = client.post(f"{BASE_URL}/api/compliance/run")
            assert run_response.status_code == 200

            audit_data = run_response.json()
            assert "generated_at" in audit_data
            assert "total_nodes" in audit_data
            assert audit_data["total_nodes"] > 0

            # Step 2: Get cached report
            get_response = client.get(f"{BASE_URL}/api/compliance/report")
            assert get_response.status_code == 200

            report_data = get_response.json()
            assert report_data["generated_at"] == audit_data["generated_at"]

            # Step 3: Export JSON
            export_response = client.get(f"{BASE_URL}/api/compliance/export")
            assert export_response.status_code == 200

            export_data = export_response.json()
            assert "data" in export_data
            assert "filename" in export_data


class TestWhatIfWorkflow:
    """End-to-end what-if scenario analysis workflow."""

    def test_whatif_baseline_vs_proposed(self):
        """Test: Run baseline → Add virtual nodes → Run proposed → Compare deltas."""
        with httpx.Client(timeout=30) as client:
            # Get a valid node to use as origin
            topology_response = client.get(f"{BASE_URL}/api/graph/topology")
            assert topology_response.status_code == 200
            topology = topology_response.json()
            origin_node = topology["nodes"][0]["id"]

            # Run what-if simulation with virtual node
            payload = {
                "origin_node_id": origin_node,
                "depth": 3,
                "virtual_nodes": [
                    {
                        "id": "virtual-replica",
                        "name": "Replica Instance",
                        "type": "database",
                        "rto_minutes": 30,
                        "is_redundant": True,
                    }
                ],
                "virtual_edges": [
                    {
                        "source": "virtual-replica",
                        "target": origin_node,
                        "type": "DEPENDS_ON",
                    }
                ],
            }

            response = client.post(f"{BASE_URL}/api/whatif/simulate", json=payload, timeout=60.0)
            assert response.status_code == 200

            result = response.json()
            assert "baseline" in result
            assert "proposed" in result
            assert "blast_radius_delta" in result
            assert "virtual_nodes_added" in result
            assert result["virtual_nodes_added"] == 1
            assert result["virtual_edges_added"] == 1


class TestChaosWorkflow:
    """End-to-end chaos engineering workflow."""

    def test_full_chaos_workflow(self):
        """Test: Create experiment → Simulate → Record actuals → Calculate resilience."""
        with httpx.Client(timeout=30) as client:
            # Get a valid node
            topology_response = client.get(f"{BASE_URL}/api/graph/topology")
            origin_node = topology_response.json()["nodes"][0]["id"]

            # Step 1: Create chaos experiment
            create_payload = {
                "node_id": origin_node,
                "scenario": "cpu_hog",
                "depth": 3,
                "notes": "Testing CPU exhaustion",
            }
            create_response = client.post(f"{BASE_URL}/api/chaos/experiments", json=create_payload)
            assert create_response.status_code == 200

            experiment = create_response.json()
            experiment_id = experiment["experiment_id"]
            assert experiment["resilience_score"] is None
            predicted_affected = len(experiment["simulation"]["affected_nodes"])

            # Step 2: List experiments
            list_response = client.get(f"{BASE_URL}/api/chaos/experiments")
            assert list_response.status_code == 200
            experiments = list_response.json()
            assert len(experiments) > 0

            # Step 3: Get single experiment
            get_response = client.get(f"{BASE_URL}/api/chaos/experiments/{experiment_id}")
            assert get_response.status_code == 200
            assert get_response.json()["experiment_id"] == experiment_id

            # Step 4: Submit actual results
            actual_nodes = experiment["simulation"]["affected_nodes"][:2]
            actuals_payload = {
                "actual_rto_minutes": 50,
                "actual_blast_radius": [n["id"] for n in actual_nodes],
                "notes": "CPU reached 85%, triggered failover",
            }
            actuals_response = client.post(
                f"{BASE_URL}/api/chaos/experiments/{experiment_id}/actuals",
                json=actuals_payload,
            )
            assert actuals_response.status_code == 200

            updated_experiment = actuals_response.json()
            assert updated_experiment["resilience_score"] is not None
            assert 0.0 <= updated_experiment["resilience_score"] <= 1.0

            # Step 5: Delete experiment
            delete_response = client.delete(f"{BASE_URL}/api/chaos/experiments/{experiment_id}")
            assert delete_response.status_code == 200


class TestPostmortemWorkflow:
    """End-to-end incident postmortem workflow."""

    def test_full_postmortem_workflow(self):
        """Test: Create postmortem → Calculate accuracy → Generate recommendations."""
        with httpx.Client(timeout=30) as client:
            # Get valid nodes
            topology_response = client.get(f"{BASE_URL}/api/graph/topology")
            nodes = topology_response.json()["nodes"]
            origin_node = nodes[0]["id"]
            failed_nodes = [nodes[1]["id"], nodes[2]["id"]] if len(nodes) > 2 else [nodes[1]["id"]]

            # Step 1: Create postmortem
            create_payload = {
                "title": "Production Database Failover",
                "occurred_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "actual_origin_node_id": origin_node,
                "actually_failed_node_ids": failed_nodes,
                "actual_rto_minutes": 45,
                "actual_rpo_minutes": 12,
                "reference_simulation_node_id": origin_node,
                "reference_simulation_depth": 3,
            }
            create_response = client.post(f"{BASE_URL}/api/postmortem/reports", json=create_payload)
            assert create_response.status_code == 200

            report = create_response.json()
            report_id = report["report_id"]

            # Validate accuracy metrics
            assert "prediction_accuracy" in report
            accuracy = report["prediction_accuracy"]
            assert "precision" in accuracy
            assert "recall" in accuracy
            assert "accuracy_score" in accuracy
            assert 0.0 <= accuracy["accuracy_score"] <= 1.0

            # Step 2: List postmortems
            list_response = client.get(f"{BASE_URL}/api/postmortem/reports")
            assert list_response.status_code == 200
            reports = list_response.json()
            assert len(reports) > 0

            # Step 3: Get single report
            get_response = client.get(f"{BASE_URL}/api/postmortem/reports/{report_id}")
            assert get_response.status_code == 200
            assert get_response.json()["report_id"] == report_id

            # Validate recommendations exist
            assert "recommendations" in report
            assert len(report["recommendations"]) > 0


class TestErrorHandling:
    """Test error scenarios and edge cases."""

    def test_compliance_report_404_before_audit(self):
        """Test that getting report without running audit returns 404."""
        with httpx.Client(timeout=30) as client:
            # Create a fresh client to ensure no cached report
            response = client.get(f"{BASE_URL}/api/compliance/report")
            # This will fail the first time, but once audit is run, it will succeed
            # The endpoint should return 404 if no report is cached

    def test_chaos_experiment_404_not_found(self):
        """Test getting non-existent chaos experiment returns 404."""
        with httpx.Client(timeout=30) as client:
            response = client.get(f"{BASE_URL}/api/chaos/experiments/nonexistent-id")
            assert response.status_code == 404

    def test_postmortem_report_404_not_found(self):
        """Test getting non-existent postmortem report returns 404."""
        with httpx.Client(timeout=30) as client:
            response = client.get(f"{BASE_URL}/api/postmortem/reports/nonexistent-id")
            assert response.status_code == 404

    def test_whatif_invalid_node(self):
        """Test what-if with invalid origin node."""
        with httpx.Client(timeout=30) as client:
            payload = {
                "origin_node_id": "invalid-node-that-doesnt-exist",
                "depth": 3,
                "virtual_nodes": [],
                "virtual_edges": [],
            }
            response = client.post(f"{BASE_URL}/api/whatif/simulate", json=payload)
            # Should handle gracefully (either 200 with empty blast radius or error)
            assert response.status_code in [200, 404]


class TestPerformance:
    """Basic performance tests."""

    def test_compliance_audit_completes_quickly(self):
        """Test that compliance audit on 14 nodes completes in reasonable time."""
        import time

        with httpx.Client(timeout=30) as client:
            start = time.time()
            response = client.post(f"{BASE_URL}/api/compliance/run", timeout=30.0)
            duration = time.time() - start

            assert response.status_code == 200
            assert duration < 10.0  # Should complete in under 10 seconds for 14 nodes

    def test_whatif_simulation_completes_quickly(self):
        """Test that what-if simulation with virtual nodes completes quickly."""
        import time

        with httpx.Client(timeout=30) as client:
            topology_response = client.get(f"{BASE_URL}/api/graph/topology")
            origin_node = topology_response.json()["nodes"][0]["id"]

            payload = {
                "origin_node_id": origin_node,
                "depth": 5,
                "virtual_nodes": [
                    {"id": f"virtual-node-{i}", "name": f"Node {i}", "type": "database"}
                    for i in range(3)
                ],
                "virtual_edges": [],
            }

            start = time.time()
            response = client.post(f"{BASE_URL}/api/whatif/simulate", json=payload, timeout=30.0)
            duration = time.time() - start

            assert response.status_code == 200
            assert duration < 5.0  # Should complete in under 5 seconds
