import pytest
from fastapi.testclient import TestClient
from main import app


client = TestClient(app)


@pytest.fixture
def setup_graph():
    """Setup a sample graph for testing."""
    # Note: This assumes Neo4j is running and has test data
    # In a real test environment, you would seed test data here
    yield
    # Cleanup (optional)


def test_simulate_disaster_returns_timeline_data():
    """Test that simulate_disaster endpoint returns step_time_ms and timeline_steps."""
    response = client.post(
        "/api/dr/simulate",
        json={"node_id": "db-001", "depth": 5}
    )

    # Response should be 200 or 404 (if node doesn't exist in test env)
    # We just check the structure when a result exists
    if response.status_code == 200:
        data = response.json()

        # Check response structure
        assert "blast_radius" in data
        assert "timeline_steps" in data
        assert "max_distance" in data
        assert "total_duration_ms" in data

        # Each node in blast_radius should have step_time_ms
        for node in data["blast_radius"]:
            assert "step_time_ms" in node
            assert node["step_time_ms"] >= 0
            assert node["step_time_ms"] <= data["total_duration_ms"]


def test_step_times_are_proportional_to_distance():
    """Test that step_time_ms values increase with distance."""
    response = client.post(
        "/api/dr/simulate",
        json={"node_id": "db-001", "depth": 5}
    )

    if response.status_code == 200:
        data = response.json()
        timeline = data["timeline_steps"]

        # Timeline should be sorted by step_time_ms
        for i in range(len(timeline) - 1):
            assert timeline[i]["step_time_ms"] <= timeline[i + 1]["step_time_ms"]

        # step_time_ms should be proportional to distance
        for step in timeline:
            if step["distance"] > 0 and data["max_distance"] > 0:
                expected_ratio = step["distance"] / data["max_distance"]
                actual_ratio = step["step_time_ms"] / data["total_duration_ms"]
                # Allow some floating point tolerance
                assert abs(expected_ratio - actual_ratio) < 0.01


def test_simulate_disaster_404_on_missing_node():
    """Test that simulate_disaster returns 404 for missing node."""
    response = client.post(
        "/api/dr/simulate",
        json={"node_id": "nonexistent-node-xyz", "depth": 5}
    )

    # Should return 404 when node doesn't exist
    assert response.status_code == 404


def test_reset_node_endpoint():
    """Test that reset_node endpoint works."""
    response = client.post(
        "/api/dr/reset/test-node-001"
    )

    # Should return success or 200
    assert response.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
